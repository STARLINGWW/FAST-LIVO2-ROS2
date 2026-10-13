# Shared Windows-side configuration for the FAST-LIVO2 drivers.
#
# Usage from any driver script in this directory:
#     . "$PSScriptRoot\site.ps1"
#
# Everything can be overridden with environment variables; the defaults match
# the documented Windows + WSL2 + Docker layout, so existing commands keep
# working. Drivers that only target native Ubuntu 22.04 do not source this file.

$ProjectDir = if ($env:FASTLIVO2_PROJECT) { $env:FASTLIVO2_PROJECT } else { (Resolve-Path (Join-Path $PSScriptRoot '..')).Path }
$WslDistro = if ($env:FASTLIVO2_WSL_DISTRO) { $env:FASTLIVO2_WSL_DISTRO } else { 'FASTLIVO-Ubuntu-22.04' }
$WslUser = if ($env:FASTLIVO2_WSL_USER) { $env:FASTLIVO2_WSL_USER } else { 'livo' }
$Ros1Container = if ($env:FASTLIVO2_ROS1_CONTAINER) { $env:FASTLIVO2_ROS1_CONTAINER } else { 'fastlivo2-ros1' }
$Ros2Workspace = if ($env:FASTLIVO2_WS) { $env:FASTLIVO2_WS } else { "/home/$WslUser/repro/fastlivo2_ws" }
$Ros2Datasets = if ($env:FASTLIVO2_DATASETS) { $env:FASTLIVO2_DATASETS } else { "/home/$WslUser/repro/datasets" }
$Ros1Entrypoint = if ($env:FASTLIVO2_ROS1_ENTRYPOINT) { $env:FASTLIVO2_ROS1_ENTRYPOINT } else { '/usr/local/bin/fastlivo-entrypoint' }
# Inside the ROS1 container the repository is mounted at $Ros1Mount and the bags
# live in the container's own /datasets (see docs/12).
$Ros1Mount = if ($env:FASTLIVO2_ROS1_MOUNT) { $env:FASTLIVO2_ROS1_MOUNT } else { '/work' }
$Ros1Datasets = if ($env:FASTLIVO2_ROS1_DATASETS) { $env:FASTLIVO2_ROS1_DATASETS } else { '/datasets' }
$RosDomainId = if ($env:ROS_DOMAIN_ID) { $env:ROS_DOMAIN_ID } else { '73' }

function ConvertTo-WslPath {
    param([Parameter(Mandatory = $true)][string]$WindowsPath)
    $full = (Resolve-Path -LiteralPath $WindowsPath).Path
    $drive = $full.Substring(0, 1).ToLower()
    return '/mnt/' + $drive + ($full.Substring(2) -replace '\\', '/')
}

$LinuxProject = ConvertTo-WslPath $ProjectDir
$LinuxScripts = "$LinuxProject/scripts"
$LinuxResults = "$LinuxProject/results/runs"

function Enter-Ros2Shell([string]$Command) {
    $wrapped = "source /opt/ros/humble/setup.bash; source $Ros2Workspace/install/setup.bash; export ROS_DOMAIN_ID=$RosDomainId ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp; $Command"
    & wsl -d $WslDistro -u $WslUser --exec bash -lc $wrapped
}

function Enter-Ros1Shell([string[]]$CommandArgs) {
    & docker exec $Ros1Container $Ros1Entrypoint @CommandArgs
}
