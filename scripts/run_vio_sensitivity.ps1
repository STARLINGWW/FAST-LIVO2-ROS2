$ErrorActionPreference='Stop'
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $taskRoot
. (Join-Path $PSScriptRoot 'site.ps1')
$variants=@('release_vio','restore_cov','restore_normal','restore_raycast')
foreach($variant in $variants){
  $pairPassed=$true
  foreach($ros in @(1,2)){
    $name="exp07_ros${ros}_paperlidar_${variant}_1x"
    $run=Join-Path $taskRoot "results/runs/$name"
    if(Test-Path -LiteralPath $run){
      $prior=Get-Content (Join-Path $run 'run.json') -Raw | ConvertFrom-Json
      $ok=($prior.status -eq 'playback_completed' -and $prior.algorithm_exit_after_signal -eq 0)
      Write-Output "EXISTING $name valid=$ok"
    }else{
      Write-Output "START $name $(Get-Date -Format o)"
      $log=Join-Path $taskRoot "results/${name}_harness.log"
      if($ros -eq 1){
        $cfg="$Ros1Mount/configs/experiments/HILTI22_paper_lidar_${variant}_ros1.yaml"
        Enter-Ros1Shell @('python3', "$Ros1Mount/scripts/run_ros1_bag.py", "$Ros1Datasets/hilti_exp07_3topics.bag", $name, '--rate', 1, '--dataset', 'HILTI22', '--image-enabled', 1, '--config-file', $cfg) > $log 2>&1
      }else{
        $cfg="$LinuxProject/configs/experiments/HILTI22_paper_lidar_${variant}_ros2.yaml"
        $cmd="python3 $LinuxScripts/run_ros2_bag.py $Ros2Datasets/hilti_exp07_ros2 $name --rate 1 --dataset HILTI22 --image-enabled 1 --config-file $cfg --output-root $LinuxResults"
        Enter-Ros2Shell $cmd > $log 2>&1
      }
      $state=Get-Content (Join-Path $run 'run.json') -Raw | ConvertFrom-Json
      $ok=($LASTEXITCODE -eq 0 -and $state.status -eq 'playback_completed' -and $state.algorithm_exit_after_signal -eq 0)
      Write-Output "RESULT $name valid=$ok $(Get-Date -Format o)"
    }
    if(-not $ok){$pairPassed=$false;break}
  }
  if($variant -eq 'restore_cov' -and $pairPassed){
    Write-Output 'PHYSICAL_STABILITY_ONLY: restoring covariance avoided extreme divergence; evaluate position error separately.'
  }
}
