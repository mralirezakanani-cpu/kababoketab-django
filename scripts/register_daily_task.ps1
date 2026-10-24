# Registers the Windows scheduled task for the daily price/stock sync bot.
# Run: powershell -ExecutionPolicy Bypass -File scripts\register_daily_task.ps1
$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$bat = Join-Path $projectRoot "scripts\daily_sync.bat"
$action = New-ScheduledTaskAction -Execute $bat -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At 04:00
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 6)
Register-ScheduledTask -TaskName "KababBookDailySync" -Action $action -Trigger $trigger -Settings $settings -Description "Kabab-o Ketab daily supplier price/stock sync (qoqnoosp, cheshmehdis, gbook)" -Force
Write-Host "Task KababBookDailySync registered for 04:00 daily."
