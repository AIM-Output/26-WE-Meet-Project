<#
  Windows 작업 스케줄러에 e클래스 자동 수집을 등록/해제한다.
  "사용자가 로그인되어 있을 때만" 실행 → Windows 비밀번호를 저장할 필요가 없다.
  창은 숨김(powershell -WindowStyle Hidden)으로 실행되며, 출력은 state\sync.log 에 쌓인다.

  등록 (기본: 4시간마다):
      powershell -ExecutionPolicy Bypass -File .\register-task.ps1
  간격 지정:
      powershell -ExecutionPolicy Bypass -File .\register-task.ps1 -IntervalHours 6
  매일 특정 시각:
      powershell -ExecutionPolicy Bypass -File .\register-task.ps1 -DailyAt 07:30
  해제:
      powershell -ExecutionPolicy Bypass -File .\register-task.ps1 -Remove
#>
param(
  [int]$IntervalHours = 4,
  [string]$DailyAt = "",
  [string]$TaskName = "eClass-Agent-Sync",
  [switch]$Remove
)

$ErrorActionPreference = "Stop"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path

if ($Remove) {
  if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "작업 '$TaskName' 삭제됨."
  } else {
    Write-Host "작업 '$TaskName' 이(가) 없습니다."
  }
  return
}

$runner = Join-Path $dir "run-sync.cmd"
if (-not (Test-Path $runner)) { throw "run-sync.cmd 를 찾을 수 없습니다: $runner" }

# 창을 띄우지 않도록 숨긴 powershell 로 run-sync.cmd 를 호출
$psArg = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command `"& '$runner'`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $psArg -WorkingDirectory $dir

if ($DailyAt) {
  $trigger = New-ScheduledTaskTrigger -Daily -At $DailyAt
  $when = "매일 $DailyAt"
} else {
  # -Once + 무기한 반복 (알려진 방식: Repetition 속성을 따로 만들어 덮어쓴다)
  $trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(2))
  $repTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours $IntervalHours) -RepetitionDuration (New-TimeSpan -Days 3650)
  $trigger.Repetition = $repTrigger.Repetition
  $when = "$IntervalHours 시간마다"
}

# 로그인 직후에도 한 번 실행 (컴퓨터를 켜면 곧 갱신). 부팅 직후 네트워크 지연을 감안해 1분 지연.
$logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$logon.Delay = "PT1M"

# 로그인되어 있을 때만 실행 → Windows 비밀번호 불필요.
# 실패(예: 막 켜서 인터넷 미연결) 시 5분 간격으로 최대 3회 자동 재시도.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)

# -User + -Settings (LogonType 생략 시 "로그인 중에만 실행", 비밀번호 불필요)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($trigger, $logon) -Settings $settings -User $env:USERNAME -Force -Description "전남대 e클래스 개인 자료 자동 수집" | Out-Null

Write-Host "작업 '$TaskName' 등록 완료 ($when + 로그인 시, 로그인 중에만 실행, 창 숨김, 실패 시 3회 재시도)."
Write-Host "로그: $dir\state\sync.log"
Write-Host "지금 한 번 실행해 보기:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "상태 확인:               Get-ScheduledTaskInfo -TaskName '$TaskName'"
Write-Host "해제:                    powershell -ExecutionPolicy Bypass -File .\register-task.ps1 -Remove"
