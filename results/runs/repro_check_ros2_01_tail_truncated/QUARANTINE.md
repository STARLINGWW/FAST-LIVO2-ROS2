# Quarantined: fixed 8 s drain truncated the tail

Clean run on a dedicated `ROS_DOMAIN_ID=137` with no competing process and no timestamp jumps,
but coverage was only 63.19 s of 74.01 s (85.4%) because the node was still ~11 s behind the 1x
playback when the harness's fixed 8 s drain ended. Per-frame cost stayed healthy
(LIO mean 26.6 ms, p95 47.3 ms), so this was not estimator starvation but a harness limitation:
the harnesses now drain until the pose stream stops advancing.

Details: `evidence/quarantined_verification_runs.md`.
