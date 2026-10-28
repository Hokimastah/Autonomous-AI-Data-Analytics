# Adjust $Project to the folder where you extracted the ZIP.
# Runs hourly using Windows Task Scheduler; analysis is skipped when input + goal were already processed.
$Project = "C:\autonomous_analytics_full"
$Python = Join-Path $Project ".venv\Scripts\python.exe"
$Script = Join-Path $Project "main.py"
$Action = New-ScheduledTaskAction -Execute $Python -Argument "`"$Script`" watch --once" -WorkingDirectory $Project
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) -RepetitionInterval (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName "LocalAutonomousAnalytics" -Action $Action -Trigger $Trigger -Description "Run local analytics on changed datasets" -Force
