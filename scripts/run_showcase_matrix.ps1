$ErrorActionPreference = 'Stop'
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $taskRoot
. (Join-Path $PSScriptRoot 'site.ps1')
$pythonTool = Join-Path $taskRoot '.venv-tools/Scripts/python.exe'
$cases = @(
  @{ros=1; run='retail_ros1_showcase'; source='Retail_Street_from_ros2_mirror.bag'; camera='/left_camera/image'; input='data/raw/Retail_Street_from_ros2_mirror.bag'; dataset='avia'},
  @{ros=2; run='retail_ros2_showcase'; source='Retail_Street'; camera='/left_camera/image'; input='data/raw/Retail_Street_from_ros2_mirror.bag'; dataset='avia'},
  @{ros=1; run='hilti_ros1_showcase'; source='hilti_exp14_3topics.bag'; camera='/alphasense/cam0/image_raw'; input='data/derived/hilti_exp14_3topics.bag'; dataset='HILTI22'},
  @{ros=2; run='hilti_ros2_showcase_retry01'; source='hilti_exp14_ros2'; camera='/alphasense/cam0/image_raw'; input='data/derived/hilti_exp14_3topics.bag'; dataset='HILTI22'},
  @{ros=1; run='exp07_ros1_release_showcase'; source='hilti_exp07_3topics.bag'; camera='/alphasense/cam0/image_raw'; input='data/derived/hilti_exp07_3topics.bag'; dataset='HILTI22'},
  @{ros=2; run='exp07_ros2_release_showcase'; source='hilti_exp07_ros2'; camera='/alphasense/cam0/image_raw'; input='data/derived/hilti_exp07_3topics.bag'; dataset='HILTI22'}
)
foreach($case in $cases) {
  $run=Join-Path $taskRoot "results/runs/$($case.run)"
  $meta=Join-Path $run 'run.json'
  $done=$false
  if(Test-Path -LiteralPath $meta) {
    $prior=Get-Content -LiteralPath $meta -Raw | ConvertFrom-Json
    if($prior.status -eq 'playback_completed' -and $prior.algorithm_exit_after_signal -eq 0 -and
       (Test-Path -LiteralPath (Join-Path $run 'all_downsampled_points.pcd'))) {
      $done=$true
    } else {throw "Existing unverified showcase: $run"}
  }
  if(-not $done) {
    if(Test-Path -LiteralPath $run){throw "Run path already exists: $run"}
    Write-Output "START $($case.run) $(Get-Date -Format o)"
    $log=Join-Path $taskRoot "results/$($case.run)_harness.log"
    if($case.ros -eq 1){
      Enter-Ros1Shell @('python3', "$Ros1Mount/scripts/run_ros1_bag.py", "$Ros1Datasets/$($case.source)", $case.run, '--rate', 1, '--dataset', $case.dataset, '--save-map', '--record-visual') > $log 2>&1
    } else {
      $command="python3 $LinuxScripts/run_ros2_bag.py $Ros2Datasets/$($case.source) $($case.run) --rate 1 --dataset $($case.dataset) --save-map --record-visual --output-root $LinuxResults"
      Enter-Ros2Shell $command > $log 2>&1
    }
    if($LASTEXITCODE -ne 0){throw "Showcase run failed: $($case.run). See $log"}
    Write-Output "PASS run $($case.run) $(Get-Date -Format o)"
  } else {Write-Output "SKIP verified run $($case.run)"}
  $map=Join-Path $run 'all_downsampled_points.pcd'
  $trajectory=Join-Path $run 'trajectory.tum'
  $mapOut=Join-Path $taskRoot "results/maps/$($case.run)"
  $videoDir=Join-Path $taskRoot "results/videos/$($case.run)"
  if(-not (Test-Path -LiteralPath (Join-Path $mapOut 'map_metrics.json'))) {
    & $pythonTool scripts/render_pcd_map.py $map --trajectory $trajectory --output $mapOut > "results/render_$($case.run)_map.log" 2>&1
    if($LASTEXITCODE -ne 0){throw "Map rendering failed: $($case.run)"}
  }
  $video=Join-Path $videoDir 'full_replay_1x.mp4'
  if(-not (Test-Path -LiteralPath (Join-Path $videoDir 'video_metrics.json'))) {
    $record=Join-Path $run ('registered_ros'+$case.ros+$(if($case.ros -eq 1){'.bag'}else{''}))
    if($case.ros -eq 2){$record=Join-Path $run 'registered_samples_ros2.npz'}
    & $pythonTool scripts/render_replay_video.py $case.input $record $map --trajectory $trajectory --image-topic $case.camera --format "ros$($case.ros)" --output $video --fps 5 > "results/render_$($case.run)_video.log" 2>&1
    if($LASTEXITCODE -ne 0){throw "Video rendering failed: $($case.run)"}
  }
  Write-Output "PASS visuals $($case.run) $(Get-Date -Format o)"
}
