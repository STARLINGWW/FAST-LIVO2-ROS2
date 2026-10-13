#!/usr/bin/env bash
# LEGACY WSL entry point (kept so older notes/commands keep working).
#
# It is now a thin wrapper around the cross-platform builder:
#     scripts/build_ros2_workspace.sh
#
# Differences from the historical behaviour: the workspace comes from
# FASTLIVO2_WS (default $HOME/repro/fastlivo2_ws) instead of a hard-coded
# per-user path, and the build no longer has to run as root (no chown/runuser
# dance) as long as your own user owns the workspace.
#
#   scripts/build_humble.sh                       # same as before on this machine
#   FASTLIVO2_WS=$HOME/other_ws scripts/build_humble.sh
set -eo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/build_ros2_workspace.sh" "$@"
