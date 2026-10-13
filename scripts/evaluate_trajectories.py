"""Timestamp-associated, fixed-scale SE(3) trajectory comparison with explicit provenance."""
import argparse
import json
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation, Slerp
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def load(path):
    a = np.loadtxt(path, comments='#', ndmin=2)
    if a.shape[1] != 8 or len(a) < 3 or not np.all(np.isfinite(a)):
        raise ValueError(f'Invalid TUM trajectory: {path}')
    if np.any(np.diff(a[:, 0]) <= 0):
        raise ValueError(f'Timestamps must be strictly increasing: {path}')
    norm = np.linalg.norm(a[:, 4:], axis=1)
    if np.max(np.abs(norm - 1)) > 0.01:
        raise ValueError(f'Invalid quaternion norms: {path}')
    return a


def main():
    p = argparse.ArgumentParser()
    p.add_argument('reference', type=Path)
    p.add_argument('estimate', type=Path)
    p.add_argument('--reference-kind', choices=['ros1_baseline', 'ros1_baseline_interpolated', 'ground_truth', 'sparse_ground_truth'], required=True)
    p.add_argument('--max-time-diff', type=float, default=0.02)
    p.add_argument('--max-interpolation-gap', type=float, default=0.25)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    ref, est = load(args.reference), load(args.estimate)
    if args.reference_kind == 'ground_truth':
        right = np.searchsorted(ref[:, 0], est[:, 0], side='right')
        bounds = (right > 0) & (right <= len(ref)) & (est[:, 0] <= ref[-1, 0])
        selected = np.flatnonzero(bounds)
        j = right[selected].clip(max=len(ref)-1)
        gaps = ref[j, 0] - ref[j-1, 0]
        selected = selected[gaps <= args.max_interpolation_gap]
        e = est[selected]
        if len(e) < 3:
            raise ValueError('Insufficient ground-truth coverage for interpolation')
        j = right[selected].clip(max=len(ref)-1)
        rpos = np.column_stack([np.interp(e[:, 0], ref[:, 0], ref[:, k]) for k in (1, 2, 3)])
        rquat = Slerp(ref[:, 0], Rotation.from_quat(ref[:, 4:]))(e[:, 0]).as_quat()
        r = np.column_stack([e[:, 0], rpos, rquat])
        association = 'interpolate_ground_truth_to_estimate_time'
        reference_coverage = float(np.count_nonzero((ref[:, 0] >= e[0, 0]) &
                                                     (ref[:, 0] <= e[-1, 0])) / len(ref)) if len(e) else 0
    elif args.reference_kind in ('sparse_ground_truth','ros1_baseline_interpolated'):
        # Association to fixed reference times preserves asynchronous ROS1/ROS2 phase.
        right = np.searchsorted(est[:, 0], ref[:, 0], side='right')
        selected = np.flatnonzero((right > 0) & (right <= len(est)) & (ref[:, 0] <= est[-1, 0]))
        j = right[selected].clip(max=len(est)-1)
        selected = selected[(est[j, 0] - est[j-1, 0]) <= args.max_interpolation_gap]
        r = ref[selected]
        if len(r) < 3:
            raise ValueError('Insufficient estimated trajectory coverage for sparse truth')
        epos = np.column_stack([np.interp(r[:, 0], est[:, 0], est[:, k]) for k in (1, 2, 3)])
        equat = Slerp(est[:, 0], Rotation.from_quat(est[:, 4:]))(r[:, 0]).as_quat()
        e = np.column_stack([r[:, 0], epos, equat])
        association = ('interpolate_estimate_to_sparse_ground_truth_time' if args.reference_kind=='sparse_ground_truth'
                       else 'interpolate_estimate_to_ros1_reference_time')
        reference_coverage = len(r) / len(ref)
    else:
        right = np.searchsorted(ref[:, 0], est[:, 0]).clip(0, len(ref) - 1)
        left = np.maximum(right - 1, 0)
        idx = np.where(abs(ref[left, 0] - est[:, 0]) <= abs(ref[right, 0] - est[:, 0]), left, right)
        match = abs(ref[idx, 0] - est[:, 0]) <= args.max_time_diff
        used, selected = set(), []
        for i in np.flatnonzero(match):
            if int(idx[i]) not in used:
                used.add(int(idx[i])); selected.append(i)
        e, r = est[selected], ref[idx[selected]]
        association = 'nearest_one_to_one'
        reference_coverage = len(e) / len(ref)
    if len(e) < 3:
        raise ValueError('Insufficient timestamp matches; do not invent a time shift')
    x, y = e[:, 1:4], r[:, 1:4]
    u, _, vt = np.linalg.svd((x - x.mean(0)).T @ (y - y.mean(0)))
    correction = np.diag([1., 1., np.linalg.det(vt.T @ u.T)])
    rotation = vt.T @ correction @ u.T
    translation = y.mean(0) - rotation @ x.mean(0)
    aligned = x @ rotation.T + translation
    error = np.linalg.norm(aligned - y, axis=1)
    raw_error = np.linalg.norm(x - y, axis=1)
    re = Rotation.from_quat(e[:, 4:]).as_matrix()
    rr = Rotation.from_quat(r[:, 4:]).as_matrix()
    rpe_t, rpe_r = [], []
    for i, stamp in enumerate(e[:, 0]):
        if args.reference_kind == 'sparse_ground_truth':
            break
        right = int(np.searchsorted(e[:, 0], stamp + 1.0))
        candidates = [k for k in (right - 1, right) if i < k < len(e)]
        if not candidates:
            continue
        j = min(candidates, key=lambda k: abs(e[k, 0] - stamp - 1.0))
        if abs(e[j, 0] - stamp - 1.) > 0.05:
            continue
        dr = rr[i].T @ rr[j]
        de = re[i].T @ re[j]
        tr = rr[i].T @ (y[j] - y[i])
        te = re[i].T @ (x[j] - x[i])
        rpe_t.append(float(np.linalg.norm(te - tr)))
        rpe_r.append(float(np.degrees(Rotation.from_matrix(dr.T @ de).magnitude())))
    def rmse(values):
        return float(np.sqrt(np.mean(np.square(values)))) if len(values) else None
    metric = {'ground_truth':'ATE', 'sparse_ground_truth':'sparse_position_error',
              'ros1_baseline':'baseline_trajectory_difference',
              'ros1_baseline_interpolated':'baseline_trajectory_difference'}[args.reference_kind]
    result = {'reference': str(args.reference), 'estimate': str(args.estimate),
              'reference_kind': args.reference_kind, 'metric': metric,
              'alignment': 'SE3, scale fixed to 1', 'association': association,
              'max_time_difference_s': args.max_time_diff,
              'max_interpolation_gap_s': args.max_interpolation_gap,
              'reference_rows': len(ref), 'estimate_rows': len(est), 'matched_rows': len(e),
              'estimate_association_fraction': None if args.reference_kind == 'sparse_ground_truth' else len(e) / len(est),
              'reference_association_fraction': reference_coverage,
              'matched_span_s': float(e[-1, 0] - e[0, 0]),
              'aligned_rmse_m': rmse(error), 'aligned_median_m': float(np.median(error)),
              'aligned_p95_m': float(np.percentile(error, 95)), 'aligned_max_m': float(error.max()),
              'unaligned_rmse_m': rmse(raw_error),
              'rpe_1second_pairs': len(rpe_t), 'rpe_translation_rmse_m': rmse(rpe_t),
              'rpe_rotation_rmse_deg': rmse(rpe_r),
              'alignment_rotation': rotation.tolist(), 'alignment_translation': translation.tolist()}
    if args.reference_kind == 'sparse_ground_truth':
        singular = np.linalg.svd(y-y.mean(0), compute_uv=False)
        result['sparse_reference_points'] = len(r)
        result['sparse_alignment_condition_ratio'] = float(singular[-1]/singular[0])
        result['sparse_quaternions_are_placeholders'] = True
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'metrics.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    if args.reference_kind == 'ground_truth':
        np.savetxt(args.output / 'matched_reference.tum', r, fmt='%.9f')
        np.savetxt(args.output / 'matched_estimate.tum', e, fmt='%.9f')
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    axes[0].plot(y[:, 0], y[:, 1], label=args.reference_kind)
    axes[0].plot(aligned[:, 0], aligned[:, 1], label='estimate, SE3 aligned', alpha=.85)
    axes[0].set(xlabel='x [m]', ylabel='y [m]', title='Matched trajectory'); axes[0].axis('equal'); axes[0].legend()
    axes[1].plot(e[:, 0] - e[0, 0], error)
    axes[1].set(xlabel='Elapsed sensor time [s]', ylabel='Position difference [m]', title=f'{metric}: RMSE {rmse(error):.4f} m')
    for ax in axes: ax.grid(alpha=.25)
    fig.savefig(args.output / 'trajectory_comparison.png', dpi=160)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
