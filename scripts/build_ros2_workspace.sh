#!/usr/bin/env bash
# Build the FAST-LIVO2 ROS2 workspace on Ubuntu 22.04 (WSL2 or native, x86_64 or aarch64).
#
#   scripts/build_ros2_workspace.sh                      # default workspace: $HOME/repro/fastlivo2_ws
#   FASTLIVO2_WS=$HOME/xplat_ws scripts/build_ros2_workspace.sh
#   scripts/build_ros2_workspace.sh --jobs 6 --rebuild-sdk
#
# Steps: (1) checks sources and ROS, (2) builds Livox-SDK2 into /usr/local if missing,
# (3) assembles <workspace>/src from this repository, (4) colcon build with the
# release/ROS2 flags the code requires.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WS="${FASTLIVO2_WS:-$HOME/repro/fastlivo2_ws}"
ROS_DISTRO="${ROS_DISTRO:-humble}"
JOBS="${FASTLIVO2_BUILD_JOBS:-4}"
SUDO="${SUDO:-sudo}"
REBUILD_SDK=0
SKIP_SDK=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --workspace) WS="$2"; shift 2 ;;
    --jobs) JOBS="$2"; shift 2 ;;
    --rebuild-sdk) REBUILD_SDK=1; shift ;;
    --skip-sdk) SKIP_SDK=1; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

echo "== FAST-LIVO2 ROS2 workspace build =="
echo "repo    : $ROOT"
echo "ros     : $ROS_DISTRO"
echo "workspace: $WS"
echo "arch    : $(uname -m)"

[[ -d "/opt/ros/${ROS_DISTRO}" ]] || { echo "ROS2 ${ROS_DISTRO} missing; run scripts/install_deps_ubuntu2204.sh first" >&2; exit 1; }

# ---------------------------------------------------------------- sources ---
missing_sources=()
[[ -d "$ROOT/ros2/FAST-LIVO2" ]] || missing_sources+=("ros2/FAST-LIVO2")
[[ -d "$ROOT/ros2/rpg_vikit" ]] || missing_sources+=("ros2/rpg_vikit")
[[ -d "$ROOT/upstream/livox_ros_driver2" ]] || missing_sources+=("upstream/livox_ros_driver2")
[[ -d "$ROOT/upstream/Livox-SDK2" ]] || missing_sources+=("upstream/Livox-SDK2")
if [[ ${#missing_sources[@]} -gt 0 ]]; then
  cat >&2 <<EOF
missing sources: ${missing_sources[*]}
The repository does not ship third-party or dataset content. Fetch the pinned
revisions first (one command, verifies SHA256 where a pin exists):
    python3 $ROOT/scripts/fetch_pinned_sources.py
EOF
  exit 1
fi

# -------------------------------------------------------------- Livox SDK ---
if [[ "${SKIP_SDK}" == "0" ]]; then
  if [[ "${REBUILD_SDK}" == "1" || ! -e /usr/local/lib/liblivox_lidar_sdk_shared.so ]]; then
    echo "-- building Livox-SDK2 (needs sudo for /usr/local install)"
    cmake -S "$ROOT/upstream/Livox-SDK2" -B "$ROOT/upstream/Livox-SDK2/build" -DCMAKE_BUILD_TYPE=Release
    cmake --build "$ROOT/upstream/Livox-SDK2/build" -j"$JOBS"
    ${SUDO} cmake --install "$ROOT/upstream/Livox-SDK2/build"
    ${SUDO} ldconfig
  else
    echo "-- Livox-SDK2 already installed (use --rebuild-sdk to force)"
  fi
fi

# ------------------------------------------------------------- workspace ----
mkdir -p "$WS/src"
echo "-- syncing sources into $WS/src"
for pair in "ros2/FAST-LIVO2:FAST-LIVO2" "ros2/rpg_vikit:rpg_vikit" "upstream/livox_ros_driver2:livox_ros_driver2"; do
  src="$ROOT/${pair%%:*}"; name="${pair##*:}"
  mkdir -p "$WS/src/$name"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete --exclude '.git' --exclude 'build' --exclude 'install' "$src/" "$WS/src/$name/"
  else
    rm -rf "$WS/src/$name"; mkdir -p "$WS/src/$name"
    cp -r "$src/." "$WS/src/$name/"
    rm -rf "$WS/src/$name/.git"
  fi
done

# The estimator writes its pose output into src/FAST-LIVO2/Log/result/<seq>.txt and
# PCD exports into Log/pcd; both directories must exist or every write fails with
# "open fail". Drop the third-party ground-truth files that ride along with the
# upstream port, then recreate the (empty) output directories.
rm -rf "$WS/src/FAST-LIVO2/Log/result/ntu_viral"
mkdir -p "$WS/src/FAST-LIVO2/Log/result" "$WS/src/FAST-LIVO2/Log/pcd"
touch "$WS/src/FAST-LIVO2/Log/result/.gitkeep" "$WS/src/FAST-LIVO2/Log/pcd/.gitkeep"

# livox_ros_driver2 ships both ROS1 and ROS2 metadata; the ROS2 build needs the
# package xml and launch directory selected explicitly.
driver="$WS/src/livox_ros_driver2"
cp "$driver/package_ROS2.xml" "$driver/package.xml"
rm -rf "$driver/launch"
cp -r "$driver/launch_ROS2" "$driver/launch"

# ------------------------------------------------------------------ build ---
echo "-- colcon build (jobs=$JOBS)"
set +u
source "/opt/ros/${ROS_DISTRO}/setup.bash"
set -u
(
  cd "$WS"
  CMAKE_BUILD_PARALLEL_LEVEL="$JOBS" colcon build --symlink-install --executor sequential \
    --cmake-args -DCMAKE_BUILD_TYPE=Release -DROS_EDITION=ROS2 -DDISTRO_ROS="${ROS_DISTRO}"
)

cat <<EOF

== build finished ==
workspace : $WS
env       : export FASTLIVO2_WS=$WS
            source /opt/ros/${ROS_DISTRO}/setup.bash
            source $WS/install/setup.bash
next      : python3 $ROOT/scripts/run_ros2_bag.py <bag> <run_id> --rate 1.0 \\
                --dataset HILTI22 --output-root $ROOT/results/runs
(see docs/12_跨平台安装与运行.md for data preparation and verification)
EOF
