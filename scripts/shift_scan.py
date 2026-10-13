"""Scan a constant time shift between an estimate and continuous ground truth.

The estimator writes poses at its own sensor timestamps; a clock offset between
the bag header stamps and the reference file would show up as a systematic error
that grows with speed. This script re-runs the same interpolate-then-SE(3)-align
evaluation used by ``evaluate_trajectories.py`` for a range of constant shifts so
that a suspicious ATE can be checked against that explanation.
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))


def load(path):
    array = np.loadtxt(path, comments='#', ndmin=2)
    if array.shape[1] != 8 or len(array) < 3 or not np.all(np.isfinite(array)):
        raise ValueError(f'Invalid TUM trajectory: {path}')
    return array


def ate_at_shift(reference, estimate, shift, max_gap):
    moved = estimate.copy()
    moved[:, 0] += shift
    right = np.searchsorted(reference[:, 0], moved[:, 0], side='right')
    inside = (right > 0) & (right <= len(reference)) & (moved[:, 0] <= reference[-1, 0])
    selected = np.flatnonzero(inside)
    if len(selected) < 3:
        return None
    index = right[selected].clip(max=len(reference) - 1)
    gaps = reference[index, 0] - reference[index - 1, 0]
    selected = selected[gaps <= max_gap]
    moved = moved[selected]
    if len(moved) < 3:
        return None
    target = np.column_stack([np.interp(moved[:, 0], reference[:, 0], reference[:, k])
                              for k in (1, 2, 3)])
    source = moved[:, 1:4]
    u, _, vt = np.linalg.svd((source - source.mean(0)).T @ (target - target.mean(0)))
    correction = np.diag([1., 1., np.linalg.det(vt.T @ u.T)])
    rotation = vt.T @ correction @ u.T
    translation = target.mean(0) - rotation @ source.mean(0)
    error = np.linalg.norm(source @ rotation.T + translation - target, axis=1)
    return float(np.sqrt(np.mean(np.square(error)))), int(len(moved))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('reference', type=Path)
    parser.add_argument('estimate', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--limit', type=float, default=0.5)
    parser.add_argument('--step', type=float, default=0.02)
    parser.add_argument('--max-interpolation-gap', type=float, default=0.25)
    args = parser.parse_args()
    reference, estimate = load(args.reference), load(args.estimate)
    scan = []
    for shift in np.arange(-args.limit, args.limit + args.step / 2, args.step):
        value = ate_at_shift(reference, estimate, float(shift), args.max_interpolation_gap)
        if value is not None:
            scan.append({'shift_s': float(shift), 'ate_rmse_m': value[0], 'matched_rows': value[1]})
    if not scan:
        raise RuntimeError('No shift produced a usable association')
    best = min(scan, key=lambda row: row['ate_rmse_m'])
    result = {'reference': str(args.reference), 'estimate': str(args.estimate),
              'metric': 'ATE RMSE over constant estimate-time shifts',
              'alignment': 'SE3, scale fixed to 1',
              'association': 'interpolate_ground_truth_to_estimate_time',
              'limit_s': args.limit, 'step_s': args.step,
              'max_interpolation_gap_s': args.max_interpolation_gap,
              'best_shift_s': best['shift_s'], 'best_rmse_m': best['ate_rmse_m'],
              'best_matched_rows': best['matched_rows'],
              'zero_shift_rmse_m': next(row['ate_rmse_m'] for row in scan if abs(row['shift_s']) < 1e-9),
              'scan': scan}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'scan'}, indent=2))


if __name__ == '__main__':
    main()
