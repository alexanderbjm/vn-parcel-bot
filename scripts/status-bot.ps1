param([string]$TaskName = "VN Parcel Bot")
$root = Split-Path -Parent $PSScriptRoot
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($task) {
    $task | Get-ScheduledTaskInfo | Select-Object LastRunTime, LastTaskResult, NextRunTime
    "State: $($task.State)"
}
else {
    "Task '$TaskName' not installed."
}
Get-CimInstance Win32_Process -Filter "Name like 'python%.exe'" |
    Where-Object { $_.CommandLine -match 'vn_parcel_bot' } |
    Select-Object ProcessId, CreationDate
$log = Join-Path $root "logs\bot.log"
if (Test-Path $log) { Get-Content $log -Tail 20 }
$err = Join-Path $root "logs\startup-error.log"
if (Test-Path $err) { "--- startup-error.log ---"; Get-Content $err -Tail 5 }
