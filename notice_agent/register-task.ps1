<#
  Windows 작업 스케줄러에 장학 공지 주기 수집(파이프라인)을 등록/해제한다.  (기능명세서 DF-5 ① "수 시간 간격")
  "사용자가 로그인되어 있을 때만" 실행 → Windows 비밀번호를 저장할 필요가 없다.
  창은 숨김으로 실행되며, 출력은 data\logs\pipeline.log 에 쌓인다.

  등록 (기본: 6시간마다):
      powershell -ExecutionPolicy Bypass -File .\register-task.ps1
  간격 지정 / 매일 특정 시각:
      powershell -ExecutionPolicy Bypass -File .\register-task.ps1 -IntervalHours 4
      powershell -ExecutionPolicy Bypass -File .\register-task.ps1 -DailyAt 07:00
  해제:
      powershell -ExecutionPolicy Bypass -File .\register-task.ps1 -Remove
#>
param(
  [int]$IntervalHours = 6,
  [string]$DailyAt = "",
  [string]$TaskName = "NoticeAgent-Scholarship",
  [switch]$Remove
)

$ErrorActionPreference = "Stop"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path

if ($Remove) {
  if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Task '$TaskName' removed."
  } else {
    Write-Host "Task '$TaskName' not found."
  }
  return
}

$runner = Join-Path $dir "run-pipeline.cmd"
if (-not (Test-Path $runner)) { throw "run-pipeline.cmd not found: $runner" }

$psArg = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command `"& '$runner'`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $psArg -WorkingDirectory $dir

if ($DailyAt) {
  $trigger = New-ScheduledTaskTrigger -Daily -At $DailyAt
  $when = "daily at $DailyAt"
} else {
  $trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(2))
  $repTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours $IntervalHours) -RepetitionDuration (New-TimeSpan -Days 3650)
  $trigger.Repetition = $repTrigger.Repetition
  $when = "every $IntervalHours hours"
}

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 40) -MultipleInstances IgnoreNew -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -User $env:USERNAME -Force -Description "Univ-Us notice_agent: scholarship notice collect/match/draft (F11)" | Out-Null

Write-Host "Task '$TaskName' registered ($when, runs only while logged on, hidden window)."
Write-Host "Log:     $dir\data\logs\pipeline.log"
Write-Host "Run now: Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Status:  Get-ScheduledTaskInfo -TaskName '$TaskName'"
Write-Host "Remove:  powershell -ExecutionPolicy Bypass -File .\register-task.ps1 -Remove"
