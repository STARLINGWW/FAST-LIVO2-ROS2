$ErrorActionPreference='Stop'
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $taskRoot
. (Join-Path $PSScriptRoot 'site.ps1')
$cases=@(
  @{ros=1;run='exp07_ros1_released_1x';image=1;paper=$false},
  @{ros=2;run='exp07_ros2_released_1x';image=1;paper=$false},
  @{ros=1;run='exp07_ros1_paper_1x';image=1;paper=$true},
  @{ros=2;run='exp07_ros2_paper_retry01_1x';image=1;paper=$true},
  @{ros=1;run='exp07_ros1_paper_lio_1x';image=0;paper=$true},
  @{ros=2;run='exp07_ros2_paper_lio_1x';image=0;paper=$true}
)
foreach($case in $cases){
  $folder=Join-Path $taskRoot "results/runs/$($case.run)"
  if(Test-Path -LiteralPath $folder){
    $prior=Get-Content -LiteralPath (Join-Path $folder 'run.json') -Raw | ConvertFrom-Json
    if($prior.status -eq 'playback_completed' -and $prior.algorithm_exit_after_signal -eq 0){
      Write-Output "SKIP verified $($case.run)"
      continue
    }
    throw "Existing unverified run: $folder"
  }
  Write-Output "START $($case.run) $(Get-Date -Format o)"
  $log=Join-Path $taskRoot "results/$($case.run)_harness.log"
  if($case.ros -eq 1){
    $taskArgs=@('python3',"$Ros1Mount/scripts/run_ros1_bag.py","$Ros1Datasets/hilti_exp07_3topics.bag",$case.run,'--rate','1','--dataset','HILTI22','--image-enabled',$case.image)
    if($case.paper){$taskArgs+=@('--config-file',"$Ros1Mount/configs/experiments/HILTI22_paper_ros1.yaml")}
    Enter-Ros1Shell $taskArgs > $log 2>&1
  } else {
    $paperArg=if($case.paper){" --config-file $LinuxProject/configs/experiments/HILTI22_paper_ros2.yaml"}else{''}
    $command="python3 $LinuxScripts/run_ros2_bag.py $Ros2Datasets/hilti_exp07_ros2 $($case.run) --rate 1 --dataset HILTI22 --image-enabled $($case.image)$paperArg --output-root $LinuxResults"
    Enter-Ros2Shell $command > $log 2>&1
  }
  if($LASTEXITCODE -ne 0){throw "Paper-aligned run failed: $($case.run), see $log"}
  Write-Output "PASS $($case.run) $(Get-Date -Format o)"
}
