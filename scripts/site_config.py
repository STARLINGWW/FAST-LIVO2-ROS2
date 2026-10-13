"""Cross-platform path configuration for the FAST-LIVO2 reproduction.

The same code runs in three environments:

* ROS2 runner inside WSL2 (Ubuntu 22.04)      -- project on /mnt/<drive>/..., workspace in $HOME
* ROS2 runner on native Ubuntu 22.04           -- project anywhere, workspace in $HOME
* ROS1 runner inside the fastlivo2:noetic-local container -- project mounted at /work, data at /datasets

Every location can be overridden with an environment variable. The defaults
reproduce the original WSL/Docker layout, so previously recorded commands keep
working unchanged:

    FASTLIVO2_PROJECT    repository root (default: parent of this scripts/ directory)
    FASTLIVO2_WS         ROS2 workspace (default: $HOME/repro/fastlivo2_ws; container: /opt/fastlivo_ws)
    FASTLIVO2_DATASETS   bag directory (default: $HOME/repro/datasets; container: /datasets)
    FASTLIVO2_RECORDED   ROS2 visual-recording directory (default: $HOME/repro/recorded)
    FASTLIVO2_RESULTS    run output root (default: <project>/results/runs)
    FASTLIVO2_ROS1_MOUNT container mount point of the repository (default: /work)
"""
import os
from pathlib import Path

PROJECT_DIR = Path(os.environ.get('FASTLIVO2_PROJECT')
                   or Path(__file__).resolve().parents[1]).resolve()
SCRIPTS_DIR = PROJECT_DIR / 'scripts'
RESULTS_ROOT = Path(os.environ.get('FASTLIVO2_RESULTS')
                    or PROJECT_DIR / 'results' / 'runs')

# The container layout is detected from the project mount point, so the same
# runner code works both in Docker and in a plain Ubuntu 22.04 shell.
IN_ROS1_CONTAINER = PROJECT_DIR == Path(os.environ.get('FASTLIVO2_ROS1_MOUNT', '/work'))


def workspace_dir() -> Path:
    """ROS2 workspace directory (build/install/src)."""
    env = os.environ.get('FASTLIVO2_WS')
    if env:
        return Path(env)
    if IN_ROS1_CONTAINER:
        return Path('/opt/fastlivo_ws')
    return Path.home() / 'repro' / 'fastlivo2_ws'


def datasets_dir() -> Path:
    """Directory that holds the bag files (ROS1 .bag or ROS2 bag2 folders)."""
    env = os.environ.get('FASTLIVO2_DATASETS')
    if env:
        return Path(env)
    if IN_ROS1_CONTAINER:
        return Path('/datasets')
    return Path.home() / 'repro' / 'datasets'


def recorded_dir() -> Path:
    """Where ROS2 visual recordings (npz) are written before rendering."""
    env = os.environ.get('FASTLIVO2_RECORDED')
    if env:
        return Path(env)
    return Path.home() / 'repro' / 'recorded'


def describe() -> str:
    return (f'project={PROJECT_DIR} container={IN_ROS1_CONTAINER} '
            f'workspace={workspace_dir()} datasets={datasets_dir()} results={RESULTS_ROOT}')


if __name__ == '__main__':
    print(describe())
