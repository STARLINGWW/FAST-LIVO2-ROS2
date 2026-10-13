"""Run one complete ROS2 bag in an already sourced, isolated Humble shell."""
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


def stop(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGINT)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=10)


def competing_processes():
    """Other bag players or mapping nodes sharing this ROS graph.

    The reproduction host may run more than one experiment at a time (several
    agents share the machine). ROS2 selects peers by ROS_DOMAIN_ID, so a second
    player on the same domain silently injects a different time base into this
    run: the log then shows "imu time stamp Jumps" and the trajectory covers only
    a fraction of the bag. Detect that before starting.
    """
    listing = subprocess.run(['pgrep', '-af', 'fastlivo_mapping|bag play'],
                             capture_output=True, text=True).stdout
    return [line.strip() for line in listing.splitlines()
            if line.strip() and 'pgrep' not in line and 'run_ros2_bag.py' not in line]


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
    p.add_argument('--output-root', type=Path, required=True)
    args = p.parse_args()
    out = args.output_root / args.run_id
    out.mkdir(parents=True, exist_ok=False)
    workspace = site_config.workspace_dir()
    source = workspace / 'src/FAST-LIVO2'
    binary = workspace / 'install/fast_livo/lib/fast_livo/fastlivo_mapping'
    config = args.config_file or (source / 'config' / f'{args.dataset}.yaml')
    camera = source / 'config' / ('camera_pinhole.yaml' if args.dataset == 'avia' else 'camera_fisheye_HILTI22.yaml')
    for f in (config, camera):
        shutil.copyfile(f, out / f.name)
    cmd = [str(binary), '--ros-args', '-r', '__node:=laserMapping',
           '--params-file', str(config), '--params-file', str(camera),
           '-p', 'use_sim_time:=true', '-p', 'evo.pose_output_en:=true',
           '-p', f'evo.seq_name:={args.run_id}', '-p', f'common.img_en:={args.image_enabled}',
           '-p', f'pcd_save.pcd_save_en:={str(args.save_map).lower()}',
           '-p', 'pcd_save.type:=0', '-p', 'pcd_save.interval:=-1',
           '-p', 'image_save.img_save_en:=false',
           '-r', '/mavros/vision_pose/pose:=/fastlivo2/raw_vision_pose']
    player_cmd = ['ros2', 'bag', 'play', str(args.bag), '--clock', '--rate', str(args.rate),
                  '--delay', '2', '--read-ahead-queue-size', '2000']
    result = {'run_id': args.run_id, 'rate': args.rate, 'command': cmd,
              'player_command': player_cmd, 'ros_domain_id': os.environ.get('ROS_DOMAIN_ID'),
              'peak_rss_kib': 0, 'samples': [], 'status': 'started'}
    competitors = competing_processes()
    if competitors:
        result['status'] = 'failed'
        result['error'] = ('other ROS2 players or mapping nodes are already running on '
                           f'ROS_DOMAIN_ID={os.environ.get("ROS_DOMAIN_ID")}: {competitors}')
        result['competing_processes'] = competitors
        (out / 'run.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        raise SystemExit(1)
    info = yaml.safe_load((args.bag / 'metadata.yaml').read_text())['rosbag2_bagfile_information']
    duration = info['duration']['nanoseconds'] / 1e9
    deadline_seconds = duration / args.rate + 120
    result['recorded_duration_seconds'] = duration
    algorithm = player = recorder = None
    algorithm_started_wall = time.time()
    local_record = site_config.recorded_dir() / f'{args.run_id}.npz'
    try:
        with (out / 'algorithm.log').open('w') as alog, (out / 'playback.log').open('w') as blog:
            algorithm_started_wall = time.time()
            algorithm = subprocess.Popen(['stdbuf', '-oL', '-eL', *cmd], stdout=alog, stderr=subprocess.STDOUT, start_new_session=True)
            time.sleep(2)
            if algorithm.poll() is not None:
                raise RuntimeError('Algorithm exited before playback')
            if args.record_visual:
                local_record.parent.mkdir(parents=True, exist_ok=True)
                with (out / 'record.log').open('w') as record_log:
                    recorder = subprocess.Popen(['python3',
                                                 str(site_config.SCRIPTS_DIR / 'ros2_visual_capture.py'),
                                                 str(local_record)],
                                                stdout=record_log, stderr=subprocess.STDOUT, start_new_session=True)
                time.sleep(2)
                if recorder.poll() is not None:
                    raise RuntimeError('ROS2 visual-output recorder exited early')
            with (out / 'runtime_parameters.yaml').open('w') as f:
                r = subprocess.run(['ros2', 'param', 'dump', '/laserMapping'], stdout=f, stderr=subprocess.STDOUT, timeout=30)
                if r.returncode:
                    raise RuntimeError('Failed to inspect runtime parameters')
            begin = time.monotonic()
            player = subprocess.Popen(player_cmd, stdout=blog, stderr=subprocess.STDOUT, start_new_session=True)
            while player.poll() is None:
                if time.monotonic() - begin > deadline_seconds:
                    raise RuntimeError('Playback exceeded duration/rate + 120 seconds')
                if algorithm.poll() is not None:
                    raise RuntimeError('Algorithm exited during playback')
                status = Path(f'/proc/{algorithm.pid}/status').read_text()
                rss = next((int(x.split()[1]) for x in status.splitlines() if x.startswith('VmRSS:')), 0)
                result['peak_rss_kib'] = max(result['peak_rss_kib'], rss)
                result['samples'].append([round(time.monotonic() - begin, 3), rss])
                time.sleep(1)
            result['playback_exit'] = player.returncode
            result['playback_wall_seconds'] = time.monotonic() - begin
            if player.returncode:
                raise RuntimeError('ros2 bag play failed')
            result['drain_seconds'] = drain_until_stable(
                algorithm, source / 'Log/result' / f'{args.run_id}.txt')
            if recorder is not None and recorder.poll() is not None:
                raise RuntimeError('ROS2 visual-output recorder exited during playback')
            if algorithm.poll() is not None:
                raise RuntimeError('Algorithm exited unexpectedly while draining')
            result['status'] = 'playback_completed'
    except Exception as exc:
        result['status'] = 'failed'
        result['error'] = str(exc)
    finally:
        if player is not None:
            stop(player)
        if recorder is not None:
            stop(recorder)
            if recorder.returncode != 0:
                result['status'] = 'failed'
                result['error'] = result.get('error', '') + '; visual-output recorder failed to close cleanly'
        if algorithm is not None:
            if args.save_map and algorithm.poll() is None:
                os.killpg(algorithm.pid, signal.SIGINT)
                try:
                    algorithm.wait(timeout=120)
                except subprocess.TimeoutExpired:
                    os.killpg(algorithm.pid, signal.SIGTERM)
                    algorithm.wait(timeout=10)
            else:
                stop(algorithm)
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
            if local_record.exists() and local_record.stat().st_mtime >= algorithm_started_wall:
                visual_out = out / 'registered_samples_ros2.npz'
                shutil.copyfile(local_record, visual_out)
                result['visual_recording'] = str(visual_out)
            else:
                result['status'] = 'failed'
                result['error'] = result.get('error', '') + '; no fresh ROS2 visual samples generated'
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
