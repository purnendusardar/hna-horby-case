# Overnight watcher: post-processes each model run as the WSL queues finish it. Run at idle priority.
#   powershell -File scripts\overnight_watcher.ps1
# Reads model\queue_status.txt and model\queue_status_freeout.txt (written by ~/queue.sh and ~/queue2.sh in WSL).
# For every run logged "OK": post-process (criteria, PNG, impacts), map + culvert candidates, rebuild dist, regenerate docs\OVERNIGHT_REPORT.md.
# Never touches the running model, never deploys, never modifies the DEM.
$ErrorActionPreference = 'Continue'
$root = 'C:\Purnendu\Aegir'
$py = "$root\.venv\Scripts\python.exe"
$log = "$root\model\watcher.log"
$runs = @(
  @{ run='scen_aoi_5m_40mm';          mm=40;  key='40mm';          st='queue_status.txt' },
  @{ run='scen_aoi_5m_100mm';         mm=100; key='100mm';         st='queue_status.txt' },
  @{ run='scen_aoi_5m_70mm_freeout';  mm=70;  key='freeout_70mm';  st='queue_status_freeout.txt' },
  @{ run='scen_aoi_5m_40mm_freeout';  mm=40;  key='freeout_40mm';  st='queue_status_freeout.txt' },
  @{ run='scen_aoi_5m_100mm_freeout'; mm=100; key='freeout_100mm'; st='queue_status_freeout.txt' }
)
$done = @{}
function Log($m) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m" | Add-Content $log }
Log 'watcher started'
[Diagnostics.Process]::GetCurrentProcess().PriorityClass = 'Idle'
while ($true) {
  foreach ($r in $runs) {
    if ($done[$r.run]) { continue }
    $sf = "$root\model\$($r.st)"
    if (-not (Test-Path $sf)) { continue }
    $lines = @(Select-String -Path $sf -Pattern $r.run -SimpleMatch | ForEach-Object { $_.Line })
    $ok = @($lines | Where-Object { $_ -match ' OK ' })
    $failed = @($lines | Where-Object { $_ -match 'FAILED' })
    if ($ok.Count -gt 0) {
      $wall = if ($ok[-1] -match 'wall_s=(\d+)') { $Matches[1] } else { '0' }
      Log "$($r.run) finished (wall_s=$wall); post-processing"
      & $py "$root\scripts\scenario_postprocess_run.py" $r.run $r.mm --wall-s $wall --key $r.key *>> $log
      & $py "$root\scripts\scenario_map_maxdepth.py" $r.run *>> $log
      Push-Location $root; npm run build *>> $log; Pop-Location
      & $py "$root\scripts\overnight_report.py" *>> $log
      $done[$r.run] = $true
      Log "$($r.run) post-processed"
    } elseif ($failed.Count -ge 2) {
      Log "$($r.run) FAILED twice; recorded in the report"
      & $py "$root\scripts\overnight_report.py" *>> $log
      $done[$r.run] = $true
    }
  }
  if ($done.Count -ge $runs.Count) { break }
  Start-Sleep -Seconds 60
}
Log 'watcher finished: all runs handled'
