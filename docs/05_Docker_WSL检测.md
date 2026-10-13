# Docker / WSL 可用性实测

检测日期：2026-09-24，北京时间。

**结论：本地 Docker Desktop + WSL2 后端可以直接使用，可以开始构建 FAST-LIVO2 的 Linux/ROS 容器。没有必要先重装 WSL 或先创建 Ubuntu WSL 发行版。**

## 实测过程与结果

| 检查 | 结果 |
|---|---|
| 初始状态 | `docker-desktop` 为 Stopped；Docker CLI 存在，但 Linux Engine named pipe 不存在 |
| 恢复 | 启动现有 `C:\Program Files\Docker\Docker\Docker Desktop.exe`，没有安装新 Docker 或更改系统配置 |
| 引擎 | Docker 29.6.1，`linux / x86_64`，WSL2 kernel `6.18.33.2-microsoft-standard-WSL2` |
| 资源 | 28 个逻辑 CPU，16618557440 bytes 内存（约 15.48 GiB） |
| Docker Hub 拉取 | `hello-world:latest` 与 `ubuntu:20.04` 拉取成功 |
| 执行 | `hello-world` 输出 Hello from Docker；命令退出码 0 |
| Ubuntu | 容器输出 Ubuntu 20.04.6 LTS，架构 x86_64；退出码 0 |
| DNS | Ubuntu 容器中 `getent hosts github.com` 成功 |
| D 盘挂载 | 能读取 `/work/upstream/FAST-LIVO2/CMakeLists.txt` |
| D 盘写入 | 容器在 `/work/evidence/docker_bind_write_probe` 创建零字节测试标记成功 |

原始日志：[hello-world](../evidence/docker_hello_world.txt)、[Ubuntu 与目录读写](../evidence/docker_ubuntu_smoke.txt)、[主机清单](../evidence/host_inventory.json)。

本次测试使用 `--rm`，临时测试容器已退出并自动移除；两个测试镜像保留，Docker Desktop 保持运行。测试未建立 FAST-LIVO2 长期容器，也未改飞控/传感器设置。

## 通过测试的能力与尚未验证的能力

| 能力 | 状态 |
|---|---|
| WSL2 承载 Docker Linux 容器 | 已验证 |
| 从 Docker Hub 拉取上述镜像 | 已验证，不等于所有 registry 都可访问 |
| D 盘源代码/结果目录共享 | 已验证 |
| 容器 GitHub DNS | 已验证；容器内 Git clone/apt 全链路尚未验证 |
| ROS Noetic 和 FAST-LIVO2 编译/运行 | 尚未执行，已有 Dockerfile 和手册 |
| 独立 Ubuntu WSL 环境 | 未安装；只有 Docker 内部发行版 |
| RViz / OpenGL / WSLg 容器 GUI | 未测试 |
| GPU/CUDA 容器透传 | 未测试，核心算法不需要 |
| D455 USB3 透传 | 未测试 |
| Mid-360 UDP 接收 / PTP | 未测试 |
| PX4 USB/串口和 MAVROS | 未测试 |

`docker-desktop` 是 Docker 管理的内部发行版；不要直接把它当成常规 Ubuntu 装 ROS。Docker 可以独立于用户 Ubuntu WSL 发行版运行。[Docker 官方说明](https://docs.docker.com/desktop/features/wsl/)

## 日后快速复查

在 PowerShell：

```powershell
docker info --format 'Server={{.ServerVersion}} OS={{.OSType}} CPUs={{.NCPU}} Memory={{.MemTotal}}'
wsl --list --verbose
docker run --rm hello-world
docker run --rm ubuntu:20.04 cat /etc/os-release
```

如果再次出现 named pipe 连接失败，先启动 Docker Desktop，再检查引擎；本次该错误的原因就是程序未启动。详细复现见 [03 操作手册](03_本地复现操作手册.md)。

## 冷启动故障与修复（同日第二次实测）

完成首轮复现后关闭了 Docker Desktop。当天再次冷启动时出现新故障，已定位并修复，记录在此以免重复踩坑。

| 项目 | 内容 |
|---|---|
| 现象 | Docker Desktop 进程可以启动，但 `docker ps` 持续报 `failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine` |
| 后端日志 | `backend crashed ... initializing Inference manager: listening on unix://.../Docker/run/dockerInference: remove ...: The file cannot be accessed by the system.` |
| 根因 | 上次会话留下的 unix socket 占位文件（`%LOCALAPPDATA%\Docker\run\dockerInference`、`%LOCALAPPDATA%\Docker\run\dockerEthernetVfkit`、`%LOCALAPPDATA%\Docker\run\userAnalyticsOtlpHttp.sock`、`%LOCALAPPDATA%\docker-secrets-engine\engine.sock`）是指向已消失 named pipe 的 reparse point；Windows 对它们返回 `ERROR_CANT_ACCESS_FILE (1920)`，Docker 启动时的“删除旧 socket”步骤失败，backend 直接崩溃 |
| 无效尝试 | 把 `%APPDATA%\Docker\settings-store.json` 的 `EnableDockerAI` 改成 `false` **不能**阻止 Inference manager 初始化，问题依旧 |
| 有效修复 | 停掉 Docker Desktop 进程，把整个 `%LOCALAPPDATA%\Docker\run` 与 `%LOCALAPPDATA%\docker-secrets-engine` 目录改名挪开（改名成 `.stale-<时间戳>` 后缀），再启动 Docker Desktop；Docker 会重建这两个目录并正常起引擎 |
| 注意 | 失效的 socket 文件本身无法查询/删除/改名，只能整目录挪开；这些 `.stale-*` 目录可以留到重启后再清理 |
| 修复结果 | 引擎 `29.6.1` 正常；`fastlivo2:noetic-local`（`sha256:c37e61a5c612…`）与容器 `fastlivo2-ros1` 均保留，无需重建 |

一键修复脚本：[`scripts/fix_docker_desktop_stale_sockets.ps1`](../scripts/fix_docker_desktop_stale_sockets.ps1)。它只在检测到失效 socket 时动作，只做“停进程 + 目录改名挪开 + 重启并等待引擎”，不删除任何文件、镜像或卷。

```powershell
# 引擎已在运行时脚本会直接退出；检测到失效 socket 时才会执行修复
powershell -ExecutionPolicy Bypass -File scripts\fix_docker_desktop_stale_sockets.ps1
```

## A 环境（ROS1 镜像）的可恢复性

ROS1 基准镜像已导出为可直接 `docker load` 的归档，这样即使 Docker Desktop 出问题、或镜像被误删，也不必重新走一遍依赖下载与编译：

| 项目 | 值 |
|---|---|
| 归档 | `data/image_archives/fastlivo2_noetic_local_image.tar` |
| 大小 / SHA256 | 1,022,951,936 bytes / `a567931ba1dd5b2451f1fd9d9eb8d4d4901284110c45b5c629401bbfe7cba6ca` |
| 对应镜像 | `fastlivo2:noetic-local`，image id `sha256:c37e61a5c612d452fd03c2807ae58e3d19464667d1d20b8fbb8c75ae0e8b614c` |
| 内容 | `/opt/fastlivo_ws`（官方 FAST-LIVO2 构建结果）、入口脚本、ROS Noetic 依赖；**不含**容器可写层里的 `/datasets` 数据与逐次运行输出 |

```powershell
docker load -i data/image_archives/fastlivo2_noetic_local_image.tar
```

如果容器被重建，按需把数据重新放进它的 `/datasets`（这些文件在本仓库里都有原始/派生副本）：

```powershell
docker cp data/raw/Retail_Street_from_ros2_mirror.bag fastlivo2-ros1:/datasets/
docker cp data/derived/hilti_exp14_3topics.bag fastlivo2-ros1:/datasets/
docker cp data/derived/hilti_exp07_3topics.bag fastlivo2-ros1:/datasets/
docker cp data/derived/hilti_exp18_3topics.bag fastlivo2-ros1:/datasets/
```

记录见 `manifests/ros1_image_archive.json`。

## B 环境（WSL2 发行版）的可恢复性

`FASTLIVO-Ubuntu-22.04` 的虚拟磁盘就在项目目录内（注册表 BasePath 指向它），因此整个 B 环境随项目目录一起保存：

```
D:\_AAA_CODE_ALL\Tech_reproduction\FASTLIVO2_reproduction\wsl\Ubuntu2204\ext4.vhdx
```

若发行版注册丢失，用同一个 BasePath 重新导入即可（不要改目录名）：

```powershell
wsl --import FASTLIVO-Ubuntu-22.04 "D:\_AAA_CODE_ALL\Tech_reproduction\FASTLIVO2_reproduction\wsl\Ubuntu2204" "D:\_AAA_CODE_ALL\Tech_reproduction\FASTLIVO2_reproduction\wsl\Ubuntu2204\ext4.vhdx"
wsl -d FASTLIVO-Ubuntu-22.04 -u livo
```

发行版内 `/home/livo/repro/fastlivo2_ws`（含 build/install）、`/home/livo/repro/datasets` 与 `/home/livo/repro/deps` 都在该 vhdx 中，恢复后无需重新编译。
