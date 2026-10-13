"""Run the unmodified official executable and a complete ROS1 bag in its container."""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import yaml
import math

sys.path.insert(0, str(Path(__file__).resolve().parent))
import site_config


def stop(proc):
    if proc is not None and proc.poll() is None:
        os.killpg(proc.pid, signal.SIGINT)
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=10)


def competing_ros1_processes():
    """Return foreign ROS1 processes that would share this container's graph.

    A leftover roscore makes the `roscore` started below fail while the
    readiness probe still answers from the stale master; the algorithm then
    loses its master mid-run and writes no trajectory. Refuse to start instead
    of silently joining a foreign graph.
    """
    found = []
    for pattern in ('roscore', 'rosmaster', 'fastlivo_mapping', 'rosbag play'):
        probe = subprocess.run(['pgrep', '-af', pattern], capture_output=True, text=True)
        for line in probe.stdout.splitlines():
            if 'run_ros1_bag.py' in line or 'pgrep -af' in line:
                continue
            found.append(line.strip())
    return sorted(set(found))


def drain_until_stable(algorithm, trajectory, max_seconds=120, quiet_seconds=6):
    """Let the estimator consume the rest of the bag after playback ends.

    A fixed short sleep silently truncates the tail whenever the node runs behind
    the 1x playback: it drains queued sensor messages at the sensor rate rather
    than as fast as the CPU allows. Wait until the last logged pose stamp stops
    advancing, bounded by ``max_seconds``.
    """
    started = time.monotonic()
    last_stamp = None
    quiet_since = None
    while time.monotonic() - started < max_seconds:
        if algorithm.poll() is not None:
            break
        stamp = None
        if trajectory.is_file():
            lines = trajectory.read_text().splitlines()
            if lines:
                try:
                    stamp = float(lines[-1].split()[0])
                except (IndexError, ValueError):
                    stamp = None
        if stamp is not None and last_stamp is not None:
            if stamp == last_stamp:
                quiet_since = quiet_since or time.monotonic()
                if time.monotonic() - quiet_since >= quiet_seconds:
                    break
            else:
                quiet_since = None
        if stamp is not None:
            last_stamp = stamp
        time.sleep(1)
    return round(time.monotonic() - started, 3)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('bag', type=Path)
    p.add_argument('run_id')
    p.add_argument('--rate', type=float, default=1.0)
    p.add_argument('--dataset', choices=['avia', 'HILTI22'], default='avia')
    p.add_argument('--config-file', type=Path)
    p.add_argument('--image-enabled', type=int, choices=[0, 1], default=1)
    p.add_argument('--save-map', action='store_true')
    p.add_argument('--record-visual', action='store_true')
    p.add_argument('--visual-mode', choices=['bag','samples'], default='bag')
    p.add_argument('--output-root', type=Path, default=site_config.RESULTS_ROOT)
    args = p.parse_args()
    out = args.output_root / args.run_id
    out.mkdir(parents=True, exist_ok=False)
    source = site_config.workspace_dir() / 'src/FAST-LIVO2'
    config = args.config_file or (source / 'config' / f'{args.dataset}.yaml')
    camera = source / 'config' / ('camera_pinhole.yaml' if args.dataset == 'avia' else 'camera_fisheye_HILTI22.yaml')
    for f in (config, camera):
        shutil.copyfile(f, out / f.name)
    info = yaml.safe_load(subprocess.check_output(['rosbag', 'info', '--yaml', str(args.bag)]))
    (out / 'bag_info.yaml').write_text(yaml.safe_dump(info))
    result = {'run_id': args.run_id, 'rate': args.rate, 'recorded_duration_seconds': info['duration'],
              'peak_rss_kib': 0, 'samples': [], 'status': 'started'}
    competitors = competing_ros1_processes()
    if competitors:
        result['status'] = 'failed'
        result['error'] = ('other ROS1 masters/nodes are already running in this container: '
                           f'{competitors}')
        result['competing_processes'] = competitors
        (out / 'run.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        raise SystemExit(1)
    core = algorithm = player = recorder = None
    try:
        with (out / 'roscore.log').open('w') as clog, (out / 'algorithm.log').open('w') as alog, (out / 'playback.log').open('w') as blog:
            core = subprocess.Popen(['roscore'], stdout=clog, stderr=subprocess.STDOUT, start_new_session=True)
            for _ in range(30):
                ready = subprocess.run(['rosparam', 'list'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if ready.returncode == 0:
                    break
                time.sleep(1)
            else:
                raise RuntimeError('ROS master did not start')
            subprocess.run(['rosparam', 'load', str(config)], check=True)
            subprocess.run(['rosparam', 'load', str(camera), '/laserMapping'], check=True)
            for key, value in [('use_sim_time', 'true'), ('evo/pose_output_en', 'true'),
                               ('evo/seq_name', args.run_id), ('common/img_en', str(args.image_enabled)),
                               ('pcd_save/pcd_save_en', 'true' if args.save_map else 'false'),
                               ('pcd_save/type', '0'), ('pcd_save/interval', '-1'),
                               ('image_save/img_save_en', 'false')]:
                subprocess.run(['rosparam', 'set', key, value], check=True)
            subprocess.run(['rosparam', 'dump', str(out / 'runtime_parameters.yaml')], check=True)
            cmd = [str(site_config.workspace_dir() / 'devel/lib/fast_livo/fastlivo_mapping'),
                   '/mavros/vision_pose/pose:=/fastlivo2/raw_vision_pose']
            result['command'] = cmd
            algorithm_started_wall = time.time()
            algorithm = subprocess.Popen(['stdbuf', '-oL', '-eL', *cmd], stdout=alog, stderr=subprocess.STDOUT, start_new_session=True)
            time.sleep(2)
            if algorithm.poll() is not None:
                raise RuntimeError('Algorithm exited before playback')
            if args.record_visual:
                record_path = site_config.datasets_dir() / f'{args.run_id}_registered.bag'
                if args.visual_mode == 'samples':
                    record_path = site_config.datasets_dir() / f'{args.run_id}_registered.npz'
                    capture_cmd = ['python3', str(site_config.SCRIPTS_DIR / 'ros1_visual_capture.py'), str(record_path)]
                else:
                    capture_cmd = ['rosbag', 'record', '-O', str(record_path),
                                   '/aft_mapped_to_init', '/cloud_registered']
                with (out / 'record.log').open('w') as record_log:
                    recorder = subprocess.Popen(capture_cmd,
                                                stdout=record_log, stderr=subprocess.STDOUT,
                                                start_new_session=True)
                time.sleep(2)
                if recorder.poll() is not None:
                    raise RuntimeError('ROS1 visual-output recorder exited early')
            begin = time.monotonic()
            player_cmd = ['rosbag', 'play', '--clock', '--rate', str(args.rate), '--delay', '2', str(args.bag)]
            result['player_command'] = player_cmd
            player = subprocess.Popen(player_cmd, stdout=blog, stderr=subprocess.STDOUT, start_new_session=True)
            while player.poll() is None:
                if algorithm.poll() is not None:
                    raise RuntimeError('Algorithm exited during playback')
                if time.monotonic() - begin > info['duration'] / args.rate + 120:
                    raise RuntimeError('Playback exceeded duration/rate + 120 seconds')
                status = Path(f'/proc/{algorithm.pid}/status').read_text()
                rss = next((int(x.split()[1]) for x in status.splitlines() if x.startswith('VmRSS:')), 0)
                result['peak_rss_kib'] = max(result['peak_rss_kib'], rss)
                result['samples'].append([round(time.monotonic() - begin, 3), rss])
                time.sleep(1)
            result['playback_exit'] = player.returncode
            result['playback_wall_seconds'] = time.monotonic() - begin
            if player.returncode:
                raise RuntimeError('rosbag play failed')
            result['drain_seconds'] = drain_until_stable(
                algorithm, source / 'Log/result' / f'{args.run_id}.txt')
            if recorder is not None and recorder.poll() is not None:
                raise RuntimeError('ROS1 visual-output recorder exited during playback')
            if algorithm.poll() is not None:
                raise RuntimeError('Algorithm exited unexpectedly while draining')
            result['status'] = 'playback_completed'
    except Exception as exc:
        result['status'] = 'failed'
        result['error'] = str(exc)
    finally:
        stop(player)
        stop(recorder)
        if recorder is not None and recorder.returncode != 0:
            result['status'] = 'failed'
            result['error'] = result.get('error', '') + '; visual-output recorder failed to close cleanly'
        if args.save_map and algorithm is not None and algorithm.poll() is None:
            os.killpg(algorithm.pid, signal.SIGINT)
            try:
                algorithm.wait(timeout=120)
            except subprocess.TimeoutExpired:
                os.killpg(algorithm.pid, signal.SIGTERM)
                algorithm.wait(timeout=10)
        else:
            stop(algorithm)
        stop(core)
        if algorithm is not None:
            result['algorithm_exit_after_signal'] = algorithm.returncode
            if algorithm.returncode != 0:
                result['status'] = 'failed'
                result['error'] = result.get('error', '') + '; algorithm did not shut down cleanly'
        trajectory = source / 'Log/result' / f'{args.run_id}.txt'
        if trajectory.exists():
            shutil.copyfile(trajectory, out / 'trajectory.tum')
            result['trajectory_rows'] = len(trajectory.read_text().splitlines())
            stamps,positions=[],[]
            for line in trajectory.read_text().splitlines():
                words=line.split()
                if len(words)<4:continue
                stamps.append(float(words[0]));positions.append(tuple(map(float,words[1:4])))
            radii=[math.sqrt(sum(v*v for v in x)) for x in positions]
            speeds=[math.dist(positions[i],positions[i-1])/(stamps[i]-stamps[i-1])
                    for i in range(1,len(stamps)) if stamps[i]>stamps[i-1]]
            result['max_trajectory_radius_m']=max(radii) if radii else None
            result['max_segment_speed_mps']=max(speeds) if speeds else None
            result['trajectory_span_seconds']=(max(stamps)-min(stamps)) if stamps else None
            if stamps and result.get('recorded_duration_seconds'):
                coverage=(max(stamps)-min(stamps))/result['recorded_duration_seconds']
                result['trajectory_coverage_fraction']=coverage
                if coverage<0.99:
                    result['status']='incomplete_coverage'
                    result['error']=(result.get('error') or '')+(
                        f'; trajectory coverage {coverage:.3f} below 0.99; the node fell behind '
                        'playback and stopped consuming sensor data before the bag ended')
            max_radius_allowed = 200 if args.dataset == 'HILTI22' else 1000
            max_speed_allowed = 10 if args.dataset == 'HILTI22' else 50
            if not radii or any(not math.isfinite(x) for x in radii+speeds) or max(radii)>max_radius_allowed or (speeds and max(speeds)>max_speed_allowed):
                result['status']='failed'
                result['error']=result.get('error','')+'; nonphysical trajectory for this dataset'
        else:
            result['status'] = 'failed'
            result['error'] = result.get('error', '') + '; no trajectory generated'
        if args.record_visual:
            record_path = site_config.datasets_dir() / f'{args.run_id}_registered.bag'
            if args.visual_mode == 'samples':
                record_path = site_config.datasets_dir() / f'{args.run_id}_registered.npz'
            if record_path.exists() and record_path.stat().st_mtime >= algorithm_started_wall:
                output_path = out / ('registered_samples_ros1.npz' if args.visual_mode == 'samples' else 'registered_ros1.bag')
                shutil.copyfile(record_path, output_path)
                result['visual_recording'] = str(output_path)
            else:
                result['status'] = 'failed'
                result['error'] = result.get('error', '') + '; no ROS1 visual recording generated'
        if args.save_map:
            result['map_files'] = []
            for f in (source / 'Log/pcd/all_raw_points.pcd', source / 'Log/pcd/all_downsampled_points.pcd'):
                if f.exists() and f.stat().st_mtime >= algorithm_started_wall:
                    destination = out / f.name
                    shutil.copyfile(f, destination)
                    result['map_files'].append({'path': str(destination), 'bytes': destination.stat().st_size})
            if not result['map_files']:
                result['status'] = 'failed'
                result['error'] = result.get('error', '') + '; no fresh PCD map generated'
        (out / 'run.json').write_text(json.dumps(result, indent=2))
        print(json.dumps({k: v for k, v in result.items() if k != 'samples'}, indent=2))
    if result['status'] != 'playback_completed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
