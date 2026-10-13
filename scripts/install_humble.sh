#!/usr/bin/env bash
# WSL-ONLY (historical environment bootstrap)
#
# This is how the development WSL2 distribution was created: it must run as
# root inside a FRESH Ubuntu 22.04 (WSL2) instance, installs ROS2 Humble
# (desktop) from the repository's pinned apt-source deb, and creates the
# unprivileged build user (default "livo").
#
# On a normal Ubuntu 22.04 machine you do NOT need this file; use
# scripts/install_deps_ubuntu2204.sh instead, which is idempotent and does not
# touch users or mirrors.
#   TARGET_USER=myuser ./scripts/install_humble.sh
set -euo pipefail
source /etc/os-release
[[ "$VERSION_ID" == 22.04 && "$EUID" == 0 ]] || exit 2
PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_USER="${TARGET_USER:-livo}"
export DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8
# Use HTTPS mirrors while retaining Ubuntu/ROS signature verification.
cp -n /etc/apt/sources.list /etc/apt/sources.list.fastlivo-original || true
sed -i -e 's|http://archive.ubuntu.com/ubuntu/|https://mirrors.tuna.tsinghua.edu.cn/ubuntu/|g' \
       -e 's|http://security.ubuntu.com/ubuntu/|https://mirrors.tuna.tsinghua.edu.cn/ubuntu/|g' /etc/apt/sources.list
apt-get -o Acquire::Retries=3 update
apt-get install -y --only-upgrade systemd systemd-sysv udev libudev1 libsystemd0
dpkg -i "$PROJECT/downloads/ros2-apt-source_1.3.0.jammy_all.deb"
sed -i -e 's|http://packages.ros.org/ros2/ubuntu|https://mirrors.tuna.tsinghua.edu.cn/ros2/ubuntu|' \
       -e 's/^Types: deb deb-src$/Types: deb/' /etc/apt/sources.list.d/ros2.sources
apt-get -o Acquire::Retries=3 update
apt-get -o Acquire::Retries=3 install -y ros-humble-desktop ros-humble-sophus \
  ros-humble-pcl-ros ros-humble-pcl-conversions ros-humble-cv-bridge \
  ros-humble-image-transport ros-humble-compressed-image-transport \
  ros-humble-tf2-geometry-msgs ros-humble-rmw-cyclonedds-cpp \
  python3-colcon-common-extensions python3-rosdep python3-vcstool python3-venv \
  python3-pip python3-yaml build-essential cmake git rsync libfmt-dev \
  libeigen3-dev libopencv-dev libpcl-dev libboost-all-dev xvfb mesa-utils
id "$TARGET_USER" >/dev/null 2>&1 || useradd -m -s /bin/bash "$TARGET_USER"
install -d -o "$TARGET_USER" -g "$TARGET_USER" "/home/$TARGET_USER/repro" "/home/$TARGET_USER/repro/fastlivo2_ws/src"
dpkg-query -W > "$PROJECT/manifests/apt_packages_humble.tsv"
printf 'HUMBLE_INSTALL_OK\n'
