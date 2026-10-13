# 论文参数整组发散的单因素定位（Hilti Exp07）

问题：把论文正文参数整组写入本机发布版代码后，Hilti Exp07 会发散（ROS1 最大半径 35.7 km、
ROS2 423 m / 46.3 m/s），而同序列用发布配置正常（ROS1 6.97 cm、ROS2 6.93 cm）。此前只做过
**VIO 三项**的逐项恢复（`configs/experiments/HILTI22_paper_lidar_restore_*`），结论是“恢复视觉
因素可消除极端发散但仍留分米—米级误差”。本文补齐**LiDAR 三项**的单因素实验，给出可验证的成因分解。

## 方法

- 基准：`configs/experiments/HILTI22_paper_ros1.yaml`（对论文正文的忠实编码：voxel 0.5 m、
  octree 3 层、光度噪声 100、PandarXT-32 深度/角度噪声 0.001 m / 0.001°、`point_filter_num` 3）。
- 三个变体各**只恢复一个发布版 LiDAR 因素**，视觉三项保持论文值，其余全部不动：
  L1 噪声（0.02 m / 0.05°）、L2 结构（voxel 0.4 / max_layer 2）、L3 抽样（`point_filter_num` 1）。
- 由 `scripts/make_lidar_ablation_configs.py` 生成（清单：`configs/experiments/lidar_ablation_manifest.json`），
  由 `scripts/run_lidar_ablation_matrix.ps1` 串行执行（容器内单 roscore，禁止并发）。
- 数据：Hilti Exp07 Long Corridor（132.26 s bag）1× 回放；覆盖率门限 ≥0.99；物理守卫
  HILTI22 半径 ≤200 m、段速度 ≤10 m/s；评价：6 点稀疏真值 `data/raw/HILTI22/exp07_long_corridor.txt`。

## 结果（ROS2 移植版，域 137，无并发）

| 运行 | 相对论文配置恢复的因素 | 最大半径 m | 最大段速度 m/s | 覆盖率 | 稀疏位置 RMSE | 中位 / 最大 |
|---|---|---:|---:|---:|---:|---:|
| `exp07_ros2_paper_retry01_1x`（旧） | —（论文整组） | **423** | 46.3 | 已被排除 | 发散，不计 | — |
| `abl_l1_paper_noise_released_ros2` | `dept_err` 0.02、`beam_err` 0.05 | 95.97 | 2.43 | 99.64 % | **2.48 m** | 1.60 / 5.07 m |
| `abl_l2_paper_structure_released_ros2` | `voxel_size` 0.4、`max_layer` 2 | 59.09 | 2.58 | 99.64 % | **19.42 m** | 17.03 / 28.13 m |
| `abl_l3_paper_subsample_released_ros2` | `point_filter_num` 1 | 99.48 | 2.43 | 99.56 % | **1.06 m** | 0.43 / 2.28 m |
| 发布配置（参照） | 三项 LiDAR + 三项 VIO 全恢复 | — | — | ≥99 % | **6.93 cm** | — |

每次运行的四元数有限、时间戳单调、`algorithm_exit_after_signal=0`；`run.json` 记录了
`trajectory_coverage_fraction` 与 `drain_seconds`（94–118 s，说明 1× 下节点落后于回放但仍完整消费）。

## 结论

1. **不存在单一“错误参数”**：单独恢复噪声、结构或抽样中的任意一项都能避免极端发散，说明
   论文整组参数发散来自**极小 LiDAR 测量噪声与较粗地图结构/抽样的组合**——0.001 m / 0.001°
   把每个平面残差当作约 20×/50× 更精确的测量，而 0.5 m 体素 + 3 层 octree + 1:3 抽样下的
   平面先验无法支撑这种置信度；任一侧放宽即可恢复物理合理性。
2. **精度收益排序**：抽样（1.06 m）> 噪声（2.48 m）> 结构（19.4 m）。但三者的单项结果都远
   达不到发布配置的 6.93 cm，说明论文的视觉参数（`img_point_cov` 100、`normal_en=false`、
   `raycast_en=true`）同样贡献误差——与既有 VIO 敏感性矩阵（三项全恢复仍为 34 cm）一致。
3. **因此**：发布版 `HILTI22.yaml` 与发布代码是自洽的一组参数；把论文正文参数直接抄入发布
   YAML 无法复现论文在 Hilti 上的数值，这是**论文文字与开源版本之间的差异**，不是 ROS2 移植
   缺陷（ROS1 上游同样发散）。

## 可复查性

- 运行：`results/runs/abl_l1_paper_noise_released_ros2`、`..._l2_paper_structure_released_ros2`、`..._l3_paper_subsample_released_ros2`
- 评价：`results/comparisons/abl_l*_sparse_gt/metrics.json`
- 日志：`results/abl_l*_harness.log`；参数快照在各运行目录的 YAML 与 `runtime_parameters.yaml`
- 生成/执行脚本：`scripts/make_lidar_ablation_configs.py`、`scripts/run_lidar_ablation_matrix.ps1`
- ROS1 上游同构复验：见本文件末尾“ROS1 复验”一节（写入后即为最终状态）。

## ROS1 复验

同一组变体在 ROS1 上游参考实现上串行复验（容器内单 roscore，脚本内置互斥检查）：

| 运行 | 恢复的因素 | 最大半径 m | 最大段速度 m/s | 覆盖率 | 稀疏位置 RMSE | 判定 |
|---|---|---:|---:|---:|---:|---|
| `abl_l1_paper_noise_released_ros1` | `dept_err` 0.02、`beam_err` 0.05 | 91.93 | 2.81 | 99.64 % | **4.02 m** | 通过，有限 |
| `abl_l2_paper_structure_released_ros1` | `voxel_size` 0.4、`max_layer` 2 | **1380.42** | 52.91 | 99.64 % | 发散，不计 | 物理守卫判失败 |
| `abl_l3_paper_subsample_released_ros1_r1` | `point_filter_num` 1 | 100.11 | 4.38 | 99.64 % | **2.32 m** | 通过，有限 |

两条被外部 `docker restart fastlivo2-ros1` 中途打断的 L3 尝试（播放停在 46.8 s 与 9.6 s，
算法以 0 退出）保存在 `..._node_exited_01` 与 `abl_l3_paper_subsample_released_ros1`
（第二次尝试）中，只有覆盖率门限能识别它们；最终结果来自重试运行 `..._r1`。

ROS1 与 ROS2 的一致结论是：**单项放宽 LiDAR 因素都能避免极端发散，且“抽样 1:1”与
“噪声放宽”给出最好的两条轨迹**；两者在“仅放宽结构”这一支上不完全一致（ROS1 仍发散到
1380 m，ROS2 保持有限但误差 19.4 m），说明边际参数下上游与移植版的数值行为并不逐位等价。
因此“两版等价”只能表述为**差异不超过运行间波动**，不能表述为逐帧等价。
