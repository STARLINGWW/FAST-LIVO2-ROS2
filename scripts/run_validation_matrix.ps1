$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $taskRoot
. (Join-Path $PSScriptRoot 'site.ps1')
$cases = @(
    @{ros=1; run='retail_ros1_1x_02'; data='Retail_Street_from_ros2_mirror.bag'; dataset='avia'; rate=1; image=1},
    @{ros=1; run='retail_ros1_1x_03'; data='Retail_Street_from_ros2_mirror.bag'; dataset='avia'; rate=1; image=1},
    @{ros=2; run='retail_ros2_1x_02'; data='Retail_Street'; dataset='avia'; rate=1; image=1},
    @{ros=2; run='retail_ros2_1x_03'; data='Retail_Street'; dataset='avia'; rate=1; image=1},
    @{ros=1; run='hilti_ros1_half_01'; data='hilti_exp14_3topics.bag'; dataset='HILTI22'; rate=0.5; image=1},
    @{ros=1; run='hilti_ros1_1x_01'; data='hilti_exp14_3topics.bag'; dataset='HILTI22'; rate=1; image=1},
    @{ros=2; run='hilti_ros2_1x_01'; data='hilti_exp14_ros2'; dataset='HILTI22'; rate=1; image=1},
    @{ros=1; run='retail_ros1_lio_01'; data='Retail_Street_from_ros2_mirror.bag'; dataset='avia'; rate=1; image=0},
    @{ros=2; run='retail_ros2_lio_retry_01'; data='Retail_Street'; dataset='avia'; rate=1; image=0},
    @{ros=1; run='retail_ros1_half_01'; data='Retail_Street_from_ros2_mirror.bag'; dataset='avia'; rate=0.5; image=1},
    @{ros=2; run='retail_ros2_half_04'; data='Retail_Street'; dataset='avia'; rate=0.5; image=1}
)
# Run all cases serially. Failures are retained and stop the matrix for diagnosis.
foreach($case in $cases) {
    $runDir = Join-Path $taskRoot "results/runs/$($case.run)"
    if(Test-Path -LiteralPath $runDir) {
        $prior = Get-Content -LiteralPath (Join-Path $runDir 'run.json') -Raw | ConvertFrom-Json
        if($prior.status -eq 'playback_completed' -and $prior.algorithm_exit_after_signal -eq 0) {
            Write-Output "SKIP verified $($case.run)"
            continue
        }
        throw "Run directory exists but is not verified: $runDir. Review before resuming."
    }
    Write-Output "START $($case.run) $(Get-Date -Format o)"
    $log = Join-Path $taskRoot "results/$($case.run)_harness.log"
    if($case.ros -eq 1) {
        Enter-Ros1Shell @('python3', "$Ros1Mount/scripts/run_ros1_bag.py", "$Ros1Datasets/$($case.data)", $case.run, '--rate', $case.rate, '--dataset', $case.dataset, '--image-enabled', $case.image) > $log 2>&1
    } else {
        # All interpolated tokens below are fixed local case constants, not user input.
        $taskCommand = "python3 $LinuxScripts/run_ros2_bag.py $Ros2Datasets/$($case.data) $($case.run) --rate $($case.rate) --dataset $($case.dataset) --image-enabled $($case.image) --output-root $LinuxResults"
        Enter-Ros2Shell $taskCommand > $log 2>&1
    }
    if($LASTEXITCODE -ne 0) { throw "Run failed: $($case.run). See $log" }
    Write-Output "PASS $($case.run) $(Get-Date -Format o)"
}
