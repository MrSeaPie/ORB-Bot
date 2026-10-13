# ==============================================================================
#  Sets up Windows Task Scheduler to start run_bot.bat every weekday at 9:20 AM
#  (your PC's clock, which is set to Eastern time). Run it once:
#
#      powershell -ExecutionPolicy Bypass -File setup_schedule.ps1
#
#  Needs: the PC switched on (sleep is fine, the task wakes it) and you logged in.
#  To remove the schedule later:
#
#      Unregister-ScheduledTask -TaskName "ORB-Bot daily" -Confirm:$false
# ==============================================================================

$taskName = "ORB-Bot daily"
$bat = Join-Path $PSScriptRoot "run_bot.bat"

$action = New-ScheduledTaskAction -Execute $bat -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At "9:20AM"
$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 8)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "ORB-Bot: scanner, then FPB paper trader until the close (paper account only)." -Force | Out-Null

$task = Get-ScheduledTask -TaskName $taskName
Write-Host "Scheduled '$taskName': weekdays 9:20 AM -> $bat"
Write-Host "Next run: $((Get-ScheduledTaskInfo -TaskName $taskName).NextRunTime)"
