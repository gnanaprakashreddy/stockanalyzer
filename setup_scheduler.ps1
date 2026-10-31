# Registers a Windows scheduled task that runs the Portfolio Analyst every weekday.
# Usage:  powershell -ExecutionPolicy Bypass -File .\setup_scheduler.ps1 [-Time "08:00"]
param([string]$Time = "08:00", [string]$TaskName = "PortfolioAnalystDailyReport")

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $root ".venv\Scripts\python.exe"
$log = Join-Path $root "reports\agent.log"
New-Item -ItemType Directory -Force (Join-Path $root "reports") | Out-Null

$cmd = "/c `"`"$py`" `"$root\run_agent.py`" >> `"$log`" 2>&1`""
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $cmd -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Daily AI portfolio analyst report" -Force | Out-Null
Write-Host "Scheduled '$TaskName' every weekday at $Time. Reports -> $root\reports\latest.html"
