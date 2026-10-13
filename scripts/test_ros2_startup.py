"""Runtime regression: shared node, local camera parameters, float types, LIO key."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import yaml
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import site_config

ROOT = site_config.PROJECT_DIR
WS = site_config.workspace_dir()
hilti = '--hilti' in sys.argv
out = ROOT / ('results/ros2_interface_test_hilti' if hilti else 'results/ros2_interface_test')
out.mkdir(exist_ok=True)
config_name = 'HILTI22.yaml' if hilti else 'avia.yaml'
camera_name = 'camera_fisheye_HILTI22.yaml' if hilti else 'camera_pinhole.yaml'
cmd = [str(WS / 'install/fast_livo/lib/fast_livo/fastlivo_mapping'), '--ros-args',
       '--params-file', str(WS / 'src/FAST-LIVO2/config' / config_name),
       '--params-file', str(WS / 'src/FAST-LIVO2/config' / camera_name),
       '-p', 'use_sim_time:=true', '-p', 'vio.img_point_cov:=100.25',
       '-p', 'vio.outlier_threshold:=1000.5', '-p', 'lio.max_iterations:=7',
       '-r', '/mavros/vision_pose/pose:=/fastlivo2/raw_vision_pose']
with (out / 'node.log').open('w') as log:
    proc = subprocess.Popen(['stdbuf', '-oL', '-eL', *cmd], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        time.sleep(3)
        assert proc.poll() is None, 'Node failed to initialize'
        result = subprocess.run(['ros2', 'param', 'dump', '/laserMapping'], capture_output=True, text=True, timeout=20, check=True)
        (out / 'parameters.yaml').write_text(result.stdout)
        params = next(iter(yaml.safe_load(result.stdout).values()))['ros__parameters']
        # ROS2 param dump represents dotted names as nested YAML mappings.
        def get(name):
            if name in params:
                return params[name]
            value = params
            for part in name.split('.'):
                value = value[part]
            return value
        assert get('cam_width') == (720 if hilti else 1280)
        assert get('cam_model') == ('EquidistantCamera' if hilti else 'Pinhole')
        assert get('vio.img_point_cov') == 100.25
        assert get('vio.outlier_threshold') == 1000.5
        assert get('lio.max_iterations') == 7
        assert get('use_sim_time') is True
        result = {'passed': True, 'checks': ['node stays alive without sensors',
                  'calibration read from local node without parameter_blackboard',
                  'fractional photometric covariance and outlier threshold accepted',
                  'official lio.max_iterations key accepted', 'simulated clock enabled']}
        (out / 'result.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result))
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGINT)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=10)
    assert proc.returncode == 0, f'Node did not shut down cleanly: {proc.returncode}'
