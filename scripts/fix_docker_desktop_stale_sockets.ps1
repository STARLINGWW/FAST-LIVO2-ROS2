<#
Docker Desktop (Windows, WSL2 backend) 冷启动修复脚本。

症状：Docker Desktop 进程存在，但 `docker ps` 一直报
  failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine
并且 %LOCALAPPDATA%\Docker\log\host\com.docker.backend.exe.log 出现
  backend crashed ... initializing Inference manager:
  listening on unix://.../Docker/run/dockerInference: remove ...:
  The file cannot be accessed by the system.

原因：上一次会话留下的 unix socket 占位文件（指向已消失的 named pipe 的 reparse point）
在 Windows 上无法查询/删除（ERROR_CANT_ACCESS_FILE 1920），Docker 启动时的清理步骤失败，
backend 直接崩溃。

本脚本只做两件事：停掉 Docker Desktop、把含有失效 socket 的目录整目录改名挪开，
然后重新启动 Docker Desktop 并等待引擎就绪。它不删除任何文件、不清理镜像或卷。
#>
[CmdletBinding()]
param(
    [string]$DockerDesktopPath = 'C:\Program Files\Docker\Docker\Docker Desktop.exe',
    [int]$TimeoutSeconds = 300,
    [string[]]$ExtraSocketDirectories = @()
)

$ErrorActionPreference = 'Stop'

function Get-StaleDirectories {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Docker\run'),
        (Join-Path $env:LOCALAPPDATA 'docker-secrets-engine')
    ) + $ExtraSocketDirectories

    foreach ($dir in $candidates) {
        if (-not (Test-Path -LiteralPath $dir)) { continue }
        foreach ($child in (Get-ChildItem -LiteralPath $dir -Force -ErrorAction SilentlyContinue)) {
            if (-not ($child.Attributes -band [IO.FileAttributes]::ReparsePoint)) { continue }
            $null = & fsutil reparsepoint query $child.FullName 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-Output $dir
                break
            }
        }
    }
}

function Test-EngineReady {
    $job = Start-Job -ScriptBlock { docker version --format '{{.Server.Version}}' 2>$null }
    try {
        if (Wait-Job -Job $job -Timeout 8) {
            return [bool](Receive-Job $job)
        }
        return $false
    } finally {
        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
    }
}

Write-Output '== Docker Desktop stale socket recovery =='

if (Test-EngineReady) {
    Write-Output 'engine already reachable; nothing to do'
    exit 0
}

$stale = @(Get-StaleDirectories | Select-Object -Unique)
if ($stale.Count -eq 0) {
    Write-Output 'no dangling socket directories detected; start Docker Desktop manually and inspect'
    Write-Output (Join-Path $env:LOCALAPPDATA 'Docker\log\host\com.docker.backend.exe.log')
    exit 1
}

Write-Output 'stopping Docker Desktop processes'
Get-Process -Name 'Docker Desktop', 'com.docker.backend' -ErrorAction SilentlyContinue |
    Stop-Process -Force
Get-Process -Name 'docker' -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
foreach ($dir in $stale) {
    $target = "$dir.stale-$stamp"
    Move-Item -LiteralPath $dir -Destination $target -ErrorAction Continue
    if (Test-Path -LiteralPath $target) {
        Write-Output "moved aside: $dir -> $target"
    } else {
        Write-Output "WARNING: could not move aside $dir"
    }
}

if (-not (Test-Path -LiteralPath $DockerDesktopPath)) {
    Write-Output "Docker Desktop executable not found: $DockerDesktopPath"
    exit 1
}
Start-Process $DockerDesktopPath -WindowStyle Hidden

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    if (Test-EngineReady) {
        $version = docker version --format '{{.Server.Version}}'
        Write-Output "engine ready: $version"
        Write-Output 'stale directories were left in place; they can be removed after a reboot'
        exit 0
    }
    Start-Sleep -Seconds 5
}

Write-Output "engine NOT ready within $TimeoutSeconds s; inspect the backend log:"
Write-Output (Join-Path $env:LOCALAPPDATA 'Docker\log\host\com.docker.backend.exe.log')
exit 1
