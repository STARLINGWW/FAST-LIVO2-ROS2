# Quarantined: CPU contention truncated the tail

`status=playback_completed` and exit code 0 are stale: the trajectory covers 66.69 s of the
74.01 s bag (90.1%). The node fell behind the 1x playback while the CPU was shared and stopped
consuming LiDAR ~6.8 s before the end (no timestamp jumps). Kept as the worked example for the
new 99% coverage gate.

Details: `evidence/quarantined_verification_runs.md`.
