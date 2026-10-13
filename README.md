# FAST-LIVO2 本地复现与 D455 + Mid-360 + PX4 实施资料

核查日期：2026-09-24（北京时间）。本目录包含本机检查、官方源码快照、数据集选择、可执行辅助脚本和实机准备方案。

## 跨平台使用（Windows 与 Ubuntu 22.04）

同一套代码支持两种运行方式，按需选择：

| 你的机器 | 建议方式 | 入口 |
|---|---|---|
| Windows + Docker Desktop + WSL2 | ROS1 官方版跑在 Docker（Noetic），ROS2 移植版跑在 WSL2 的 Ubuntu 22.04 | [12 跨平台安装与运行](docs/12_跨平台安装与运行.md) 的 A 轨道 |
| 原生 Ubuntu 22.04（x86 或 ARM） | 直接构建 ROS2 工作区，不需要 Docker | [12 跨平台安装与运行](docs/12_跨平台安装与运行.md) 的 B 轨道 |

三条命令的骨架（依赖与细节见 12）：

```bash
scripts/install_deps_ubuntu2204.sh     # 首次：安装 ROS2 Humble 与依赖
scripts/build_ros2_workspace.sh        # 编 Livox-SDK2 + 组装工作区 + colcon build
python3 scripts/run_ros2_bag.py <bag> <run_id> --rate 1.0 --dataset HILTI22 --output-root results/runs
```

路径不再写死：Linux 侧读 `scripts/site_config.py`，Windows 侧 dot-source `scripts/site.ps1`，都可用环境变量覆盖——
`FASTLIVO2_PROJECT`、`FASTLIVO2_WS`、`FASTLIVO2_DATASETS`、`FASTLIVO2_RECORDED`、`FASTLIVO2_RESULTS`；Windows 侧另有
`FASTLIVO2_WSL_DISTRO`、`FASTLIVO2_WSL_USER`、`FASTLIVO2_ROS1_CONTAINER`。不设置时使用与本仓库文档一致的默认值。

本仓库**不含**数据集、视频、Docker 镜像与 WSL 磁盘（体积与许可原因，见 [NOTICE](NOTICE)）：数据用
`scripts/download_hf_resumable.py` 下载、`scripts/prepare_hilti.py` 转换；镜像与发行版磁盘按 [05](docs/05_Docker_WSL检测.md)
与 [11](docs/11_冷启动与并发运行规则.md) 在本机重建。

**成果入口：[论文对照、多数据集指标、视频和地图](docs/10_论文对照与多数据集成果.md)。** ROS1 原版与 ROS2 移植版均已构建，在 Retail_Street、Hilti Exp14、Hilti Exp07、Hilti Exp18 四个序列上完成 1× 真实数据回放；三个 Hilti 序列都对照了公开真值（Exp14/Exp18 连续真值，Exp07 为 6 点稀疏真值）。八段 H.264 时序视频、原生 PCD 和地图预览可在成果页查看。视觉与 LiDAR 参数敏感性矩阵现已全部执行（ROS2 两项单因素此前为空缺），另有环境冷启动复跑与独立数值复核。01–08 是准备阶段资料，其中“尚未安装/运行”的历史描述不再代表当前状态。

## 结论

1. **最新确定采用双环境：Docker Ubuntu20.04/Noetic 建立官方基准，独立 WSL2 Ubuntu22.04/Humble 验证 ROS2 移植。** 详见 [08 双环境详细计划](docs/08_双环境原版与ROS2移植验证计划.md)。i7-14700K（20 核 / 28 线程）、约 32 GB RAM、RTX 5070 Ti（16 GB）、D 盘约 544 GiB 空闲，足以作为复现工作站；核心算法不要求 CUDA。
2. **Docker + WSL2 可以使用，冷启动故障已修复。** 初检 Docker Desktop 未启动；本次已启动并成功运行 `hello-world`。之后再次冷启动时 Docker Desktop 因残留 socket 文件无法起引擎，已定位根因并给出不删除任何文件的一键修复脚本 [`scripts/fix_docker_desktop_stale_sockets.ps1`](scripts/fix_docker_desktop_stale_sockets.ps1)。不需要先安装独立 Ubuntu WSL 发行版才能使用 Docker。细分测试结果见 [Docker/WSL 检测](docs/05_Docker_WSL检测.md)。
3. **ROS1 原版与 ROS2 移植版都已运行验证。** Retail 无真值，只比较两版一致性；Hilti Exp14 使用连续真值，ROS1/ROS2 ATE RMSE 为 3.83/3.85 cm；Hilti Exp07 有六个稀疏位置真值，两版发布配置的本地误差均约 7 cm；新增 Hilti Exp18（连续真值，只覆盖前 86.6 s）每版各跑两次：ROS1 23.38–24.57 cm、ROS2 12.38–15.06 cm，而**同一版本两次运行之间就差 15.2/15.6 cm**，所以该序列只能说明精度随场景变化明显，不能用单次运行下移植结论。直接套用论文文字参数在本开源版本中会发散，诊断记录完整保留。视觉敏感性矩阵的 8 个单元已全部执行：ROS2 单独恢复法向/关闭光线投射后轨迹有限但误差达 16.10 m / 0.81 m，ROS1 在同样设置下发散。整组发散的成因分解（只恢复单项 LiDAR 参数）见 [证据文件](evidence/lidar_ablation_summary.md)。
4. **D455 + Mid-360 可以组成 FAST-LIVO2 输入，PX4 负责飞控。** 推荐先使用 Mid-360 内置 IMU 和 D455 的一路 RGB 图像；D455 深度可用于后续避障。算法运行在 PC/机载伴随计算机，不运行在普通 PX4 飞控 MCU 上。
5. 实机关键工作是**标定、跨设备时间同步、消息适配、飞控坐标变换与质量监控**。官方源码已有 `/mavros/vision_pose/pose` 发布，但不能据此认定已经适配本套硬件。
6. **结果可跨环境重启复现，并已独立复核。** Docker/WSL 重启后用同一命令重放 `coldstart_ros1_retail_01`、`repro_check_ros1_01`、`repro_check_ros2_01`，与上一轮归档轨迹的差异为 0.39 / 0.47 / 1.35 cm；Exp14 冷启动 ATE 为 ROS1 3.73 cm、ROS2 4.27 cm（归档 3.83 / 3.85 cm），即运行间波动约 0.1–0.4 cm。`scripts/audit_report_claims.py` 不依赖报告生成脚本，直接从轨迹、PCD、地图比较、evo 日志与视频重算 91 条声明，91 条一致。

## 阅读顺序

| 文件 | 内容 |
|---|---|
| [10 论文对照与成果（优先阅读）](docs/10_论文对照与多数据集成果.md) | 数据集、真值、ATE/RPE、计算耗时、地图、八段视频与论文参考值 |
| [09 实施与验证记录](docs/09_实施与验证记录.md) | 环境搭建与首轮结果的历史记录；当前结论以10为准 |
| [11 冷启动与并发运行规则](docs/11_冷启动与并发运行规则.md) | 关机后恢复步骤、容器 `/datasets` 风险、ROS_DOMAIN_ID 隔离、覆盖率门限与实测故障 |
| [08 双环境详细计划（优先阅读）](docs/08_双环境原版与ROS2移植验证计划.md) | 最新方案：官方基准、ROS2 移植、数据转换与量化验收、硬件/PX4 阶段 |
| [07 统一 ROS2 环境](docs/07_WSL22.04_ROS2统一环境.md) | B 环境：Ubuntu 22.04 + Humble、工作区隔离、ROS2 移植候选 |
| [01 本机条件](docs/01_本机条件与路线选择.md) | 实测配置、缺口、Docker/WSL/原生 Linux 的选择 |
| [02 数据集](docs/02_数据集选择与评估.md) | 官方下载入口、配置对应关系、真值与评价边界 |
| [03 本地复现](docs/03_本地复现操作手册.md) | Docker 构建、回放、输出保存、WSL 备选路线及排错 |
| [04 硬件准备](docs/04_D455_Mid360_PX4实施方案.md) | 接线、驱动、标定、同步、里程计到 PX4、分阶段验收 |
| [05 Docker/WSL 检测](docs/05_Docker_WSL检测.md) | 运行实测与明确的可用范围 |
| [06 来源与源码核查](docs/06_来源与源码核查.md) | 一手资料链接、固定版本和关键源码位置 |
| [实验记录模板](templates/实验记录.md) | 后续复现时逐项填写 |

`upstream/FAST-LIVO2/` 是官方代码的浅克隆，固定提交为 `0d2c0346107b75b59934975adec9a6eeeb913c64`。未修改其算法源码。`evidence/` 保存机器检查与容器测试记录；`scripts/` 和 `docker/` 是本次准备的辅助文件。所有标为“模板 / 待验证”的内容均不是实机测试结果。

环境入口：ROS1 使用 `docker exec -it fastlivo2-ros1 /usr/local/bin/fastlivo-entrypoint bash`；ROS2 使用 `wsl -d FASTLIVO-Ubuntu-22.04 -u livo`，再 source Humble 和 `/home/livo/repro/fastlivo2_ws/install/setup.bash`。完整命令、参数和逐次结果在成果页及 `results/runs/`。D455/Mid-360/PX4 真机尚未接入，准备工作详见04。

## 冷启动与环境恢复

关机或重启后要重新跑复现，按下面顺序恢复，不需要重建镜像或重新编译：

1. **ROS1（Docker）**：启动 Docker Desktop。如果它“进程在跑但 `docker ps` 连不上引擎”，这是上次会话残留的 socket 占位文件导致的已知故障，直接运行
   `powershell -ExecutionPolicy Bypass -File scripts\fix_docker_desktop_stale_sockets.ps1`（只停进程并把失效目录改名挪开，不删任何文件）；故障机理和实测记录见 [05](docs/05_Docker_WSL检测.md)。
2. **启动容器**：`docker start fastlivo2-ros1`（镜像 `fastlivo2:noetic-local` 与容器都在本机保留），入口 `/opt/fastlivo_ws`，`/work` 是本项目目录，`/datasets` 在镜像内。
3. **ROS2（WSL2）**：`wsl -d FASTLIVO-Ubuntu-22.04 -u livo`，发行版磁盘就在本项目 `wsl\Ubuntu2204\ext4.vhdx`，`~/repro/fastlivo2_ws`、`~/repro/datasets`、`~/repro/deps` 全部随磁盘保留；注册丢失时按 05 的 `wsl --import` 命令恢复。
4. **复查既有成果**：`./.venv-tools/Scripts/python scripts/verify_final_artifacts.py` 会重新解码八段视频、检查 PCD 点数、地图文件和成果页链接，并刷新 `evidence/final_artifact_qa.json`。

同一时刻只应有一个算法节点在跑（ROS1 与 ROS2 不要并行），否则回放覆盖率会掉到 0.99 门槛以下——这一点在共享机器上尤其明显。
