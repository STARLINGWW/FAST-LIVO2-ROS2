"""Recompute trajectory time coverage for every recorded run.

The project's G1 gate requires the estimated trajectory to cover at least 99% of
the played bag duration. Coverage was added to the run harnesses later, so this
audit re-derives it from the stored trajectory files and flags runs that were
recorded as ``playback_completed`` while actually losing part of the sequence
(for example when the node fell behind a 1x playback under shared CPU load).
"""
import json
from pathlib import Path

GATE = 0.99


def main():
    root = Path(__file__).resolve().parents[1]
    runs_dir = root / 'results/runs'
    report = {
        'gate': GATE,
        'definition': 'trajectory span (last minus first pose stamp) / played bag duration',
        'checked_runs': 0,
        'counted_violations': [],
        'excluded_violations': [],
        'missing_trajectory': [],
        'runs': [],
    }
    for run_dir in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        meta_path = run_dir / 'run.json'
        if not meta_path.is_file():
            continue
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
        status = meta.get('status')
        # A run directory carrying QUARANTINE.md was rejected by editorial review
        # (see evidence/quarantined_verification_runs.md) and is reported, not counted.
        quarantined = (run_dir / 'QUARANTINE.md').is_file()
        counted = (status == 'playback_completed' and meta.get('algorithm_exit_after_signal') == 0
                   and not quarantined)
        entry = {
            'run': run_dir.name,
            'status': status,
            'counted': counted,
            'quarantined': quarantined,
            'recorded_duration_seconds': meta.get('recorded_duration_seconds'),
        }
        report['checked_runs'] += 1
        trajectory = run_dir / 'trajectory.tum'
        if not trajectory.is_file():
            if counted:
                report['missing_trajectory'].append(run_dir.name)
            report['runs'].append(entry)
            continue
        stamps = [float(line.split()[0]) for line in trajectory.read_text().splitlines()
                  if len(line.split()) >= 4]
        entry['trajectory_rows'] = len(stamps)
        if len(stamps) >= 2:
            entry['trajectory_span_seconds'] = round(max(stamps) - min(stamps), 3)
        duration = meta.get('recorded_duration_seconds')
        if len(stamps) >= 2 and duration:
            coverage = (max(stamps) - min(stamps)) / duration
            entry['trajectory_coverage_fraction'] = round(coverage, 4)
            if coverage < GATE:
                entry['violation'] = True
                violation = {
                    'run': run_dir.name,
                    'status': status,
                    'coverage': round(coverage, 4),
                    'trajectory_span_seconds': entry['trajectory_span_seconds'],
                    'recorded_duration_seconds': duration,
                }
                report['counted_violations' if counted else 'excluded_violations'].append(violation)
        report['runs'].append(entry)
    report['counted_runs'] = sum(1 for entry in report['runs'] if entry['counted'])
    report['status'] = 'passed' if not (report['counted_violations'] or report['missing_trajectory']) else 'failed'
    destination = root / 'evidence/coverage_audit.json'
    destination.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'runs'}, indent=2))
    if report['status'] != 'passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
