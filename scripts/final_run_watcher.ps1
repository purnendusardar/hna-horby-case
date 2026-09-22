# Watches model\queue_status_final.txt and post-processes each final_aoi_5m_<mm>mm run as it finishes.
#   powershell -File scripts\final_run_watcher.ps1
$ErrorActionPreference = 'Continue'
$root = 'C:\Purnendu\Aegir'
$py = "$root\.venv\Scripts\python.exe"
$log = "$root\model\final_watcher.log"
$runs = @(
  @{ run='final_aoi_5m_40mm';  mm=40;  key='40mm' },
  @{ run='final_aoi_5m_70mm';  mm=70;  key='70mm' },
  @{ run='final_aoi_5m_100mm'; mm=100; key='100mm' }
)
$done = @{}
function Log($m) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m" | Add-Content $log }
Log 'final watcher started'
[Diagnostics.Process]::GetCurrentProcess().PriorityClass = 'Idle'
while ($true) {
  foreach ($r in $runs) {
    if ($done[$r.run]) { continue }
    $sf = "$root\model\queue_status_final.txt"
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
      Log "$($r.run) FAILED twice"
      $done[$r.run] = $true
    }
  }
  if ($done.Count -ge $runs.Count) { break }
  Start-Sleep -Seconds 30
}
Log 'final watcher finished: all runs handled'
