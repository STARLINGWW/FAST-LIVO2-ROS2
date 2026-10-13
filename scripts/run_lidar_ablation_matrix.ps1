$ErrorActionPreference='Stop'
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $taskRoot
. (Join-Path $PSScriptRoot 'site.ps1')
$cases=@(
  @{run='abl_l1_paper_noise_released_ros1';config='HILTI22_paper_noise_released_ros1.yaml'},
  @{run='abl_l2_paper_structure_released_ros1';config='HILTI22_paper_structure_released_ros1.yaml'},
  @{run='abl_l3_paper_subsample_released_ros1';config='HILTI22_paper_subsample_released_ros1.yaml'}
)
# The ROS1 container runs a single roscore, so two concurrent runs would share the graph and
# silently mix Hilti Exp07/Exp14 messages. Refuse to start while another run is active.
# The bracket in the pattern stops pgrep from matching this command's own wrapper (whose
# command line contains the pattern text), which would otherwise always look like a busy run.
$busy=[int](& docker exec $Ros1Container bash -lc 'pgrep -fc "[r]un_ros1_bag.py" || true')
if($busy -gt 0){throw "Another ROS1 run is active in $Ros1Container ($busy process); wait for it to finish."}
foreach($case in $cases){
  $folder=Join-Path $taskRoot "results/runs/$($case.run)"
  if(Test-Path -LiteralPath $folder){
    $prior=Get-Content -LiteralPath (Join-Path $folder 'run.json') -Raw | ConvertFrom-Json
    if($prior.status -eq 'playback_completed' -and $prior.algorithm_exit_after_signal -eq 0){
      Write-Output "SKIP verified $($case.run)"
      continue
    }
    if($prior.status -eq 'failed' -and $prior.error -match 'nonphysical trajectory'){
      Write-Output "RECORDED-DIVERGENCE $($case.run) max_radius=$($prior.max_trajectory_radius_m) m"
      continue
    }
    throw "Existing unverified run: $folder"
  }
  Write-Output "START $($case.run) $(Get-Date -Format o)"
  $log=Join-Path $taskRoot "results/$($case.run)_harness.log"
  Enter-Ros1Shell @('python3', "$Ros1Mount/scripts/run_ros1_bag.py", `
      "$Ros1Datasets/hilti_exp07_3topics.bag", $case.run, '--rate', 1, '--dataset', 'HILTI22', '--image-enabled', 1, `
      '--config-file', "$Ros1Mount/configs/experiments/$($case.config)") > $log 2>&1
  if($LASTEXITCODE -ne 0){
    $state=Get-Content -LiteralPath (Join-Path $folder 'run.json') -Raw | ConvertFrom-Json
    if($state.status -eq 'failed' -and $state.error -match 'nonphysical trajectory'){
      Write-Output "DIVERGED $($case.run) max_radius=$($state.max_trajectory_radius_m) m"
      continue
    }
    throw "Ablation run failed: $($case.run), see $log"
  }
  Write-Output "PASS $($case.run) $(Get-Date -Format o)"
}
