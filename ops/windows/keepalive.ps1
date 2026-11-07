# Historical attempt to keep WSL awake and disable sleep timeouts.
# A later check did not find this keepalive running. Laptop sleep still stopped
# recording. This is not a supported service and it does not guarantee wake.
# $env:USERPROFILE and $env:USERNAME are the current Windows user, not a
# substituted path. The script changes power settings if you run it.
$cfg = "$env:USERPROFILE\.wslconfig"
if (Test-Path $cfg) { Write-Output "existing .wslconfig:"; Get-Content $cfg; Copy-Item $cfg "$cfg.bak" -Force }
$txt = if (Test-Path $cfg) { Get-Content $cfg -Raw } else { "" }
if ($txt -notmatch "vmIdleTimeout") {
  if ($txt -match "\[wsl2\]") { $txt = $txt -replace "\[wsl2\]", "[wsl2]`r`nvmIdleTimeout=-1" }
  else { $txt = $txt + "`r`n[wsl2]`r`nvmIdleTimeout=-1`r`n" }
}
if ($txt -notmatch "instanceIdleTimeout") {
  if ($txt -match "\[general\]") { $txt = $txt -replace "\[general\]", "[general]`r`ninstanceIdleTimeout=-1" }
  else { $txt = $txt + "`r`n[general]`r`ninstanceIdleTimeout=-1`r`n" }
}
Set-Content -Path $cfg -Value $txt -Encoding ASCII
Write-Output "new .wslconfig:"; Get-Content $cfg

$name = "TSA-WSL-KeepAlive"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument '-NoProfile -WindowStyle Hidden -Command "wsl.exe -d Ubuntu -- sleep infinity"'
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Description "Keep WSL Ubuntu running for talk_show_analyzer recordings" -Force | Out-Null
Start-ScheduledTask -TaskName $name
Start-Sleep 5
Get-ScheduledTask -TaskName $name | Select-Object TaskName, State | Format-Table | Out-String | Write-Output
Get-CimInstance Win32_Process -Filter "Name='wsl.exe'" | Select-Object ProcessId, CommandLine | Format-List | Out-String | Write-Output
Write-Output "== power before"; powercfg /q SCHEME_CURRENT SUB_SLEEP STANDBYIDLE | Select-String "Current"
powercfg /change standby-timeout-ac 0
powercfg /change standby-timeout-dc 0
powercfg /change hibernate-timeout-ac 0
powercfg /change hibernate-timeout-dc 0
Write-Output "== power after"; powercfg /q SCHEME_CURRENT SUB_SLEEP STANDBYIDLE | Select-String "Current"
Write-Output "== battery"; Get-CimInstance Win32_Battery | Select-Object EstimatedChargeRemaining, BatteryStatus | Format-List | Out-String | Write-Output
