#!/usr/bin/env bash
# Install the Ubuntu 22.04 / ROS2 Humble dependencies of this reproduction.
#
#   scripts/install_deps_ubuntu2204.sh                 # install what is missing
#   APT_MIRROR=mirrors.aliyun.com scripts/install_deps_ubuntu2204.sh
#   scripts/install_deps_ubuntu2204.sh --check         # report only, change nothing
#
# Idempotent: packages that already exist are skipped. ROS itself is only
# installed when /opt/ros/<distro> is missing AND --auto-ros is given, because
# adding the ROS apt repository is a system-level change you may want to review.
set -euo pipefail

ROS_DISTRO="${ROS_DISTRO:-humble}"
SUDO="${SUDO:-sudo}"
APT_MIRROR="${APT_MIRROR:-}"
MODE=install
for arg in "$@"; do
  case "$arg" in
    --check) MODE=check ;;
    --auto-ros) AUTO_ROS=1 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done
AUTO_ROS="${AUTO_ROS:-0}"

APT_PACKAGES=(
  build-essential cmake git curl ca-certificates pkg-config
  libeigen3-dev libpcl-dev libopencv-dev libfmt-dev libboost-thread-dev
  python3-pip python3-yaml python3-colcon-common-extensions
  "ros-${ROS_DISTRO}-ros-base"
  "ros-${ROS_DISTRO}-rosbag2" "ros-${ROS_DISTRO}-rosbag2-storage-default-plugins"
  "ros-${ROS_DISTRO}-cv-bridge" "ros-${ROS_DISTRO}-image-transport"
  "ros-${ROS_DISTRO}-compressed-image-transport"
  "ros-${ROS_DISTRO}-pcl-ros" "ros-${ROS_DISTRO}-pcl-conversions"
  "ros-${ROS_DISTRO}-tf2-ros" "ros-${ROS_DISTRO}-sophus" "ros-${ROS_DISTRO}-rviz2"
  # needed by the camera/LiDAR drivers on a real robot, harmless on a dev box
  libudev-dev libusb-1.0-0-dev
)

echo "== target: Ubuntu 22.04 / ROS2 ${ROS_DISTRO} (mode: ${MODE}) =="
if [[ "$(lsb_release -rs 2>/dev/null || echo unknown)" != "22.04" ]]; then
  echo "WARNING: this host is not Ubuntu 22.04; the ROS2 package names below assume jammy." >&2
fi

if [[ ! -d "/opt/ros/${ROS_DISTRO}" ]]; then
  echo "ROS2 ${ROS_DISTRO} is not installed (no /opt/ros/${ROS_DISTRO})." >&2
  if [[ "${AUTO_ROS}" == "1" && "${MODE}" == "install" ]]; then
    echo "installing the ROS2 apt repository and ros-${ROS_DISTRO}-ros-base ..."
    ${SUDO} apt-get update
    ${SUDO} apt-get install -y software-properties-common curl gnupg lsb-release
    ${SUDO} add-apt-repository -y universe
    ${SUDO} apt-get update
    ${SUDO} apt-get install -y "ros-${ROS_DISTRO}-ros-base"
  else
    cat >&2 <<EOF
Install ROS2 ${ROS_DISTRO} first (official instructions:
https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html ), then re-run.
Or pass --auto-ros to let this script run:
    sudo apt install ros-${ROS_DISTRO}-ros-base
EOF
    exit 1
  fi
fi

missing=()
for pkg in "${APT_PACKAGES[@]}"; do
  dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
done

if [[ ${#missing[@]} -eq 0 ]]; then
  echo "all ${#APT_PACKAGES[@]} packages already present"
  exit 0
fi

echo "missing (${#missing[@]}): ${missing[*]}"
if [[ "${MODE}" == "check" ]]; then
  exit 1
fi

if [[ -n "${APT_MIRROR}" ]]; then
  echo "using Ubuntu mirror ${APT_MIRROR} (existing sources backed up as *.bak-fastlivo2)"
  for f in /etc/apt/sources.list; do
    [[ -f "$f.bak-fastlivo2" ]] || ${SUDO} cp "$f" "$f.bak-fastlivo2"
    ${SUDO} sed -i -e "s|http://archive.ubuntu.com/ubuntu|http://${APT_MIRROR}/ubuntu|g" \
                   -e "s|http://security.ubuntu.com/ubuntu|http://${APT_MIRROR}/ubuntu|g" "$f"
  done
fi

${SUDO} apt-get update
${SUDO} apt-get install -y --no-install-recommends "${missing[@]}"
echo
echo "done.  verify with:"
echo "  source /opt/ros/${ROS_DISTRO}/setup.bash && ros2 --version && echo \$ROS_DISTRO"
