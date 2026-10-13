# Quarantined verification runs (2026-09-24, cold-start re-verification)

Two ROS2 verification attempts were rejected after inspection. Both directories are kept
because they document failure modes that the harnesses did not previously detect.

## `results/runs/repro_check_ros2_01_contended`

- Hilti Exp14 (74.01 s bag) at 1x, finished `status=playback_completed`, exit 0, ATE 3.69 cm.
- Trajectory covered only **66.69 s of 74.01 s (90.1 %)**; the node fell behind a 1x
  playback while the CPU was shared with a Docker ROS1 job and stopped consuming LiDAR
  ~6.8 s before the end (algorithm log: `IMU and LiDAR not synced`, no timestamp jumps).
- Consequence: the run harnesses now compute `trajectory_span_seconds` /
  `trajectory_coverage_fraction` and end with `status=incomplete_coverage` below 0.99,
  which is the project's G1 gate. `scripts/audit_coverage.py` re-derives the same number
  for every stored run; all 29 previously counted runs pass it.

## `results/runs/repro_check_ros2_01_graph_collision`

- Same bag and settings, but started while another agent was playing Hilti Exp07 in the
  same ROS graph (`ROS_DOMAIN_ID=73`, identical node name `laserMapping`, same topics).
- 15,392 `imu time stamp Jumps` warnings; the two bags' IMU bases differ by 3,360,241 s
  (~38.9 d), so the node's LiDAR/IMU synchronisation collapsed. 63 trajectory rows
  spanning 6.2 s of the 74 s bag; exit code 0, so nothing but coverage exposed it.
- Consequence: `scripts/run_ros2_bag.py` now refuses to start when another
  `fastlivo_mapping` or `ros2 bag play` process is alive and records the competing
  processes in `run.json` (`status=failed`). Negative test stored in this file's history:
  the guard blocked a run while the Exp07 job was active.

## `results/runs/repro_check_ros2_01_tail_truncated`

- Same bag/settings on a dedicated `ROS_DOMAIN_ID=137` with no competing process
  (0 `imu time stamp Jumps`), clean exit, finite trajectory, 633 rows / 63.19 s of 74.01 s
  (**85.4 %**).
- Per-frame cost was healthy (LIO mean 26.6 ms, p95 47.3 ms, no frame above 100 ms), so this
  was not CPU starvation of the estimator: the node was still ~11 s behind the 1x playback
  when `ros2 bag play` exited, and the harness's fixed 8 s drain ended before the queued
  sensor messages were consumed.
- Consequence: both harnesses now call `drain_until_stable()`, which waits (bounded by 120 s)
  until the last logged pose stamp stops advancing for 6 s, and record `drain_seconds` in
  `run.json`. The fixed `sleep(8)` is gone.

Verification runs that are counted must therefore satisfy all four conditions:
exclusive ROS graph, `algorithm_exit_after_signal=0`, complete drain, and coverage >= 0.99.
