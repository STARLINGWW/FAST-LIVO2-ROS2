# Quarantined: ROS graph collision with a concurrent run

Same bag and settings, but another agent was playing Hilti Exp07 in the same ROS graph
(`ROS_DOMAIN_ID=73`, identical node name `laserMapping`). The log contains 15,392
`imu time stamp Jumps` warnings, the two bags' IMU bases differ by 3,360,241 s, and only 63
poses / 6.2 s of the 74 s bag were produced - while the exit code stayed 0.

Details: `evidence/quarantined_verification_runs.md`.
