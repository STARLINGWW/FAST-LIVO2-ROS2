param([string]$OutputDir = (Join-Path $PSScriptRoot '..\evidence'))
$ErrorActionPreference = 'Continue'
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$report = [ordered]@{
  captured_at = (Get-Date -Format o)
  os = (Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,OSArchitecture,TotalVisibleMemorySize,FreePhysicalMemory)
  cpu = (Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors)
  computer = (Get-CimInstance Win32_ComputerSystem | Select-Object HypervisorPresent,TotalPhysicalMemory)
  drives = @(Get-PSDrive -PSProvider FileSystem | Select-Object Name,Root,Used,Free)
  adapters = @(Get-NetAdapter -Physical | Select-Object Name,InterfaceDescription,Status,LinkSpeed)
  sensor_usb_matches = @(Get-PnpDevice -PresentOnly | Where-Object {$_.FriendlyName -match 'RealSense|D455|PX4|Pixhawk|Livox'} | Select-Object Class,FriendlyName,Status)
  commands = @(Get-Command git,python,wsl,docker,cmake,roscore,catkin_make -ErrorAction SilentlyContinue | Select-Object Name,Source)
  gpu = @(& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>&1 | ForEach-Object {"$_"})
  docker_summary = @(& docker info --format 'Server={{.ServerVersion}} OS={{.OSType}} Arch={{.Architecture}} CPUs={{.NCPU}} MemoryBytes={{.MemTotal}} Kernel={{.KernelVersion}}' 2>&1 | ForEach-Object {"$_"})
  docker_images = @(& docker image ls --format '{{.Repository}}:{{.Tag}} {{.Size}}' 2>&1 | ForEach-Object {"$_"})
  wsl_list = @(& python -c "import subprocess; r=subprocess.run(['wsl','--list','--verbose'],capture_output=True); print(r.stdout.decode('utf-16-le',errors='replace'))" 2>&1 | ForEach-Object {"$_"})
  wsl_version = @(& python -c "import subprocess; r=subprocess.run(['wsl','--version'],capture_output=True); print(r.stdout.decode('utf-16-le',errors='replace'))" 2>&1 | ForEach-Object {"$_"})
}
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $OutputDir 'host_inventory.json') -Encoding utf8
Write-Output (Join-Path $OutputDir 'host_inventory.json')
