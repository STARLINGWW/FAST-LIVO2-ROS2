"""Re-check the delivered FAST-LIVO2 artifacts (runs, videos, maps, report links).

Usage (from the project root, with the tools venv):

    ./.venv-tools/Scripts/python scripts/verify_final_artifacts.py

Writes evidence/final_artifact_qa.json and prints the same JSON. Exits non-zero
on the first failed assertion so the check can be used in a cold-start procedure.
"""
import json
import re
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from render_pcd_map import open_pcd  # noqa: E402  (needs sys.path above)

SHOWCASES = [
    ('retail_ros1_showcase', 'full_replay_1x.mp4'),
    ('retail_ros2_showcase', 'full_replay_1x.mp4'),
    ('hilti_ros1_showcase', 'full_replay_1x.mp4'),
    ('hilti_ros2_showcase_retry01', 'full_replay_1x.mp4'),
    ('exp07_ros1_release_light_showcase', 'full_replay_1x.mp4'),
    ('exp07_ros2_release_showcase', 'full_replay_1x.mp4'),
    ('exp18_ros1_showcase', 'full_replay_1x.mp4'),
    ('exp18_ros2_showcase', 'full_replay_1x.mp4'),
]
REPORT = ROOT / 'docs/10_论文对照与多数据集成果.md'
VIDEO_DURATION_TOLERANCE_S = 1.5
MIN_MAP_POINTS = 1000


def check_video(run_name: str, video_name: str, recorded_duration_s: float) -> dict:
    video = ROOT / 'results/videos' / run_name / video_name
    metrics = json.loads((video.parent / 'video_metrics.json').read_text(encoding='utf-8'))
    assert metrics['codec'] == 'h264', (run_name, metrics['codec'])
    assert metrics['frames'] > 100, (run_name, metrics['frames'])

    cap = cv2.VideoCapture(str(video))
    assert cap.isOpened(), run_name
    try:
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        assert frame_count == metrics['frames'], (run_name, frame_count, metrics['frames'])
        assert abs(fps - metrics['fps']) < 0.01, (run_name, fps, metrics['fps'])
        for frame_id in (0, frame_count // 2, frame_count - 2):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_id)
            ok, frame = cap.read()
            assert ok and frame.shape == (720, 1280, 3), (run_name, frame_id)
    finally:
        cap.release()

    assert abs(metrics['video_duration_s'] - recorded_duration_s) < VIDEO_DURATION_TOLERANCE_S, (
        run_name, metrics['video_duration_s'], recorded_duration_s)
    return {
        'run': run_name,
        'frames': metrics['frames'],
        'duration_s': metrics['video_duration_s'],
        'codec': 'h264',
        'cloud_events_in_video': metrics['registered_cloud_messages'],
    }


def check_run(run_name: str) -> tuple:
    run = ROOT / 'results/runs' / run_name
    meta = json.loads((run / 'run.json').read_text(encoding='utf-8'))
    assert meta['status'] == 'playback_completed', (run_name, meta.get('status'), meta.get('error'))
    assert meta['algorithm_exit_after_signal'] == 0, (run_name, meta['algorithm_exit_after_signal'])

    pcd = run / 'all_downsampled_points.pcd'
    _, cloud_meta = open_pcd(pcd)
    assert cloud_meta['points'] > MIN_MAP_POINTS, (run_name, cloud_meta['points'])
    assert cloud_meta['binary_bytes_expected'] == cloud_meta['data_bytes'], run_name

    assert (ROOT / 'results/maps' / run_name / 'map_detail.png').is_file(), run_name
    assert (ROOT / 'results/maps' / run_name / 'preview_sample.ply').is_file(), run_name
    return meta, cloud_meta


def check_report_links() -> int:
    text = REPORT.read_text(encoding='utf-8')
    links = re.findall(r'\]\(([^)\s]+)\)', text)
    missing = [
        link for link in links
        if not link.startswith(('http://', 'https://', '#'))
        and not (REPORT.parent / link.split('#')[0]).exists()
    ]
    assert not missing, missing
    return len(links)


def main() -> int:
    entries = []
    for run_name, video_name in SHOWCASES:
        meta, cloud_meta = check_run(run_name)
        entry = check_video(run_name, video_name, meta['recorded_duration_seconds'])
        entry['map_points'] = cloud_meta['points']
        entries.append(entry)
        print(f"OK {run_name}: frames={entry['frames']} map_points={entry['map_points']}")

    link_count = check_report_links()
    report = {
        'selected_showcases': entries,
        'report_local_link_count': link_count,
        'missing_local_links': [],
        'status': 'passed',
    }
    out = ROOT / 'evidence/final_artifact_qa.json'
    out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
