# Second historical keepalive (Startup-folder VBS that runs `wsl.exe sleep infinity`).
# Not found running on a later check. The recording path below is one file from
# 2026-11-04 on that laptop, kept so the command matches what was used.
# This does not guarantee Windows stays awake.
$startup = [Environment]::GetFolderPath("Startup")
$vbs = Join-Path $startup "tsa_wsl_keepalive.vbs"
Set-Content -Path $vbs -Encoding ASCII -Value 'CreateObject("WScript.Shell").Run "wsl.exe -d Ubuntu -- sleep infinity", 0, False'
Write-Output "written $vbs"
Start-Process wscript.exe -ArgumentList "`"$vbs`""
Start-Sleep 5
Get-CimInstance Win32_Process -Filter "Name='wsl.exe'" | Select-Object ProcessId, CommandLine | Format-List | Out-String | Write-Output
wsl -d Ubuntu -- bash -lc "systemctl --user list-units 'rec-*' --no-legend | cat; ls -la ~/tsa_data/recordings/2026-11-04/*/part01_150850.mp3"
