#!/usr/bin/env bash
# Read-only checks; run inside the intended Linux/ROS runtime.
set -uo pipefail
cat /etc/os-release
uname -a
free -h
df -h .
for tool in cmake g++ roscore catkin_make rosbag rospack; do
  command -v "$tool" || true
done
if command -v rosversion >/dev/null; then rosversion -d; fi
if command -v pkg-config >/dev/null; then
  for pkg in opencv4 pcl_common eigen3; do pkg-config --modversion "$pkg" || true; done
fi
if command -v rospack >/dev/null; then
  for pkg in fast_livo vikit_common vikit_ros cv_bridge; do rospack find "$pkg" || true; done
fi
