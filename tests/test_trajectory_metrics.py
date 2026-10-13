"""Synthetic tests validate the evaluator only; they are not algorithm reproduction data."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import numpy as np
from scipy.spatial.transform import Rotation

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/evaluate_trajectories.py'


class MetricTests(unittest.TestCase):
    def generate(self):
        t = np.arange(50) * .1
        xyz = np.column_stack([t, np.sin(t), np.cos(2*t)])
        rot = Rotation.from_euler('z', (t * .1)[:, None])
        return np.column_stack([1000+t, xyz, rot.as_quat()])

    def evaluate(self, ref, est):
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder)
            np.savetxt(d/'ref.tum', ref)
            np.savetxt(d/'est.tum', est)
            r = subprocess.run([sys.executable, str(SCRIPT), str(d/'ref.tum'), str(d/'est.tum'),
                                '--reference-kind', 'ground_truth', '--output', str(d/'result')],
                               capture_output=True, text=True)
            metric = d/'result/metrics.json'
            return r.returncode, json.loads(metric.read_text()) if metric.exists() else None

    def test_rigid_world_change_has_zero_ate_and_rpe(self):
        ref = self.generate()
        est = ref.copy()
        r = Rotation.from_euler('xyz', [.2, -.3, .4])
        est[:, 1:4] = r.apply(ref[:, 1:4]) + [10, -3, 2]
        est[:, 4:] = (r * Rotation.from_quat(ref[:, 4:])).as_quat()
        code, metric = self.evaluate(ref, est)
        self.assertEqual(code, 0)
        self.assertLess(metric['aligned_rmse_m'], 1e-10)
        self.assertLess(metric['rpe_translation_rmse_m'], 1e-10)
        self.assertLess(metric['rpe_rotation_rmse_deg'], 1e-9)
        self.assertEqual(metric['matched_rows'], len(ref))

    def test_scale_error_is_not_hidden(self):
        ref = self.generate(); est = ref.copy(); est[:, 1:4] *= 2
        code, metric = self.evaluate(ref, est)
        self.assertEqual(code, 0)
        self.assertGreater(metric['aligned_rmse_m'], .5)

    def test_unmatched_timestamps_fail(self):
        ref = self.generate(); est = ref.copy(); est[:, 0] += 10000
        code, metric = self.evaluate(ref, est)
        self.assertNotEqual(code, 0)
        self.assertIsNone(metric)

    def test_dense_ground_truth_interpolates_phase_shift(self):
        ref = self.generate()
        est = ref.copy()[1:-1]
        est[:, 0] += .04
        for col in (1, 2, 3):
            est[:, col] = np.interp(est[:, 0], ref[:, 0], ref[:, col])
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder)
            np.savetxt(d/'ref.tum', ref)
            np.savetxt(d/'est.tum', est)
            result = subprocess.run([sys.executable, str(SCRIPT), str(d/'ref.tum'), str(d/'est.tum'),
                                     '--reference-kind', 'ground_truth', '--output', str(d/'result')],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            metric = json.loads((d/'result/metrics.json').read_text())
            self.assertEqual(metric['matched_rows'], len(est))
            self.assertLess(metric['aligned_rmse_m'], 1e-10)

    def test_sparse_truth_scores_positions_without_fake_orientation(self):
        est = self.generate()
        truth = est[[5,13,21,29,37,45]].copy()
        truth[:,4:] = [0,0,0,1]  # Sparse benchmark placeholders.
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder)
            np.savetxt(d/'truth.tum',truth)
            np.savetxt(d/'estimate.tum',est)
            result=subprocess.run([sys.executable,str(SCRIPT),str(d/'truth.tum'),str(d/'estimate.tum'),
                                   '--reference-kind','sparse_ground_truth','--output',str(d/'out')],
                                  capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            metric=json.loads((d/'out/metrics.json').read_text())
            self.assertEqual(metric['matched_rows'],6)
            self.assertLess(metric['aligned_rmse_m'],1e-10)
            self.assertIsNone(metric['rpe_rotation_rmse_deg'])
            self.assertTrue(metric['sparse_quaternions_are_placeholders'])

    def test_ros2_phase_shift_uses_interpolated_reference_times(self):
        ref=self.generate()
        ref[:,1:4]=np.column_stack([ref[:,0]-1000, np.zeros(len(ref)),np.zeros(len(ref))])
        ref[:,4:]=[0,0,0,1]
        est=ref.copy()[1:-1]
        est[:,0]+=.025
        est[:,1]=est[:,0]-1000
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder)
            np.savetxt(d/'ref.tum',ref);np.savetxt(d/'est.tum',est)
            r=subprocess.run([sys.executable,str(SCRIPT),str(d/'ref.tum'),str(d/'est.tum'),
                              '--reference-kind','ros1_baseline_interpolated','--output',str(d/'out')],
                             capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            m=json.loads((d/'out/metrics.json').read_text())
            self.assertLess(m['aligned_rmse_m'],1e-10)
            self.assertGreater(m['matched_rows'],40)


if __name__ == '__main__':
    unittest.main()
