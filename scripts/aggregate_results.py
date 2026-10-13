"""Aggregate only validated full runs; retain failures separately for audit."""
import csv
import json
from pathlib import Path
from extract_timing_metrics import parse, describe

root=Path(__file__).resolve().parents[1]
rows=[]; failures=[]
expected={'retail':1355,'hilti':740,'exp07':1322,'exp18':1094}


BAG_FAMILIES=(('exp07','Exp07 Long Corridor','exp07'),('exp18','Hilti Exp18','exp18'),
              ('exp14','Hilti Exp14','hilti'),('retail','Retail Street','retail'))


def classify(run,name):
    """Prefer the bag actually played: run ids such as abl_l1_* do not name the dataset."""
    played=' '.join(run.get('player_command') or [])
    hay=f'{played} {name}'.lower()
    for token,label,family in BAG_FAMILIES:
        if token in hay:return label,family
    return 'Retail Street','retail'


def time_coverage(folder,run):
    """Trajectory stamp span divided by the played bag duration (G1 gate input)."""
    trajectory=folder/'trajectory.tum'
    duration=run.get('recorded_duration_seconds')
    if not trajectory.is_file() or not duration:return None
    stamps=[float(line.split()[0]) for line in trajectory.read_text().splitlines()
            if len(line.split())>=4]
    if len(stamps)<2:return None
    return (max(stamps)-min(stamps))/duration


for folder in sorted((root/'results/runs').iterdir()):
    if not folder.is_dir():
        continue
    state=folder/'run.json'
    if not state.is_file():
        kept=sorted(p.name for p in folder.iterdir())
        failures.append({'run':folder.name,'status':'no_run_json',
                         'reason':('aborted before the runner wrote run.json; retained files: '
                                   + (', '.join(kept) if kept else '(empty directory)'))})
        continue
    run=json.loads(state.read_text(encoding='utf-8'))
    if (folder/'QUARANTINE.md').is_file():
        failures.append({'run':folder.name,'status':'quarantined',
                         'reason':'rejected by editorial review; see evidence/quarantined_verification_runs.md'})
        continue
    ok=run.get('status')=='playback_completed' and run.get('algorithm_exit_after_signal')==0
    if not ok:
        failures.append({'run':folder.name,'status':run.get('status'),
                         'reason':run.get('error') or run.get('reason')})
        continue
    name=folder.name
    dataset, family = classify(run, name)
    impl='ROS2' if 'ros2' in name else 'ROS1'
    sensor_mode='LIO' if 'lio' in name else 'LIVO'
    config='paper-aligned' if 'paper' in name else 'released-config'
    base=describe(parse(folder/'algorithm.log')['LIO'])
    visual=describe(parse(folder/'algorithm.log')['VIO'])
    row={'run':name,'dataset':dataset,'implementation':impl,'mode':sensor_mode,
         'configuration':config,'bag_rate':run.get('rate'),
         'trajectory_rows':run.get('trajectory_rows'), 'lidar_frame_count':expected[family],
         'trajectory_frame_fraction':run.get('trajectory_rows',0)/expected[family],
         'trajectory_time_coverage':time_coverage(folder,run),
         'playback_wall_s':run.get('playback_wall_seconds'),
         'bag_duration_s':run.get('recorded_duration_seconds'),
         'peak_rss_mib':run.get('peak_rss_kib',0)/1024,
         'lio_mean_ms':base['mean_ms'] if base else None,
         'lio_p95_ms':base['p95_ms'] if base else None,
         'lio_max_ms':base['max_ms'] if base else None,
         'lio_frames_logged':base['frames'] if base else 0,
         'vio_mean_ms':visual['mean_ms'] if visual else None,
         'vio_p95_ms':visual['p95_ms'] if visual else None,
         'vio_frames_logged':visual['frames'] if visual else 0,
         'has_pcd':bool(run.get('map_files')),
         'has_visual_recording':bool(run.get('visual_recording'))}
    if row['trajectory_frame_fraction']<.98:
        row['coverage_attention']='below 98%'
    rows.append(row)
out=root/'results/aggregated'
out.mkdir(exist_ok=True)
with (out/'runs.csv').open('w',newline='',encoding='utf-8') as f:
    writer=csv.DictWriter(f,fieldnames=sorted({k for row in rows for k in row}))
    writer.writeheader();writer.writerows(rows)
(out/'runs.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
(out/'excluded_runs.json').write_text(json.dumps(failures,indent=2),encoding='utf-8')
print(json.dumps({'valid_runs':len(rows),'excluded_runs':len(failures),'datasets':sorted({x['dataset'] for x in rows})}))
