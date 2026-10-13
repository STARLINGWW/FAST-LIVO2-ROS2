import os
from pathlib import Path
import signal
import subprocess
import time
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import site_config

root = site_config.PROJECT_DIR
ws = site_config.workspace_dir()
lio = '--lio' in sys.argv
full = '--full' in sys.argv
cmd = ['gdb', '--batch', '-ex', 'set pagination off',
       '-ex', 'handle SIGINT nostop noprint pass', '-ex', 'run',
       '-ex', 'thread apply all bt', '--args',
       str(ws / 'install/fast_livo/lib/fast_livo/fastlivo_mapping'), '--ros-args',
       '--params-file', str(ws / 'src/FAST-LIVO2/config/avia.yaml'),
       '--params-file', str(ws / 'src/FAST-LIVO2/config/camera_pinhole.yaml'),
       '-p', 'use_sim_time:=true', '-p', 'evo.seq_name:=debug_shutdown',
       '-r', '/mavros/vision_pose/pose:=/fastlivo2/raw_vision_pose']
if lio:
    cmd.extend(['-p', 'common.img_en:=0'])
name = 'ros2_lio_shutdown_full_gdb.log' if lio and full else ('ros2_lio_shutdown_gdb.log' if lio else 'ros2_shutdown_gdb.log')
with (root / 'results' / name).open('w') as log:
    debugger = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    time.sleep(3)
    player = subprocess.Popen(['ros2', 'bag', 'play', str(site_config.datasets_dir() / 'Retail_Street'), '--clock'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    time.sleep(145 if full else 12)
    os.killpg(player.pid, signal.SIGINT)
    player.wait(timeout=10)
    children = Path(f'/proc/{debugger.pid}/task/{debugger.pid}/children').read_text().split()
    for pid in children:
        os.kill(int(pid), signal.SIGINT)
    try:
        debugger.wait(timeout=25)
    except subprocess.TimeoutExpired:
        os.killpg(debugger.pid, signal.SIGTERM)
        debugger.wait(timeout=10)
    print('gdb_exit', debugger.returncode)
