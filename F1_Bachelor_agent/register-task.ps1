<#
  Windows 작업 스케줄러에 학사일정 자동 수집을 등록/해제한다 (F1 · F1-R05). e클래스(F6)와 같은 규칙:
  매일 08:00 + 로그인할 때 앱 실행 파일(--run-module bachelor tick)을 부른다.
  - 그 시각에 PC 가 꺼져 있었거나 절전이었으면 켜지는 대로 한 번 실행한다(StartWhenAvailable).
    tick 이 '오늘 08시 이후 성공한 수집이 있으면 건너뜀'으로 하루 한 번만 돌게 막는다.
  - 실패 재시도(5·15·45분)는 tick 이 직접 한다 → 작업 스케줄러의 재시작 옵션은 쓰지 않는다.
  "사용자가 로그인되어 있을 때만" 실행 → Windows 비밀번호를 저장할 필요가 없다. 창은 숨김, 출력은 state\sync.log.

  앱의 '수집 원천' 화면(예약 수집 켜기)이 앱 번들 안의 이 파일을 부른다 (bachelor/runner.py register_task):
      powershell -ExecutionPolicy Bypass -File .\register-task.ps1 -At 08:00 -Command "& '<앱 실행 파일>' --run-module bachelor tick --log '…'"
  (tick 의 기준 시각은 환경변수 F1_SCHEDULE_AT, 기본 08:00 — 함께 바꿀 것)
  해제:
      powershell -ExecutionPolicy Bypass -File .\register-task.ps1 -Remove
#>
param(
  [string[]]$At = @("08:00"),
  [string]$TaskName = "UnivUs-F1-Academic-Sync",
  [string]$Command = "",
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

# 부를 명령 — 앱이 -Command 로 앱 실행 파일을 준다 (C0 osenv.task_command)
#   (예: & '<앱 실행 파일>' --run-module bachelor tick --log '<앱 데이터 폴더>\F1_Bachelor_agent\state\sync.log')
if (-not $Command) { throw "-Command 가 필요합니다 — 앱의 수집 원천 화면에서 예약 수집을 켜세요" }

$psArg = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command `"$Command`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $psArg -WorkingDirectory $dir

$triggers = @()
foreach ($t in $At) { $triggers += New-ScheduledTaskTrigger -Daily -At $t }
$logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$logon.Delay = "PT2M"
$triggers += $logon

# 놓친 시각은 켜지는 대로(StartWhenAvailable) · 재시도 사슬(최대 5+15+45분)을 감안해 2시간 제한 · 겹치면 새 실행은 무시
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers -Settings $settings -User $env:USERNAME -Force -Description "유니버스 F1 전남대 학사일정·학사공지·내 소속 공지 자동 수집 (매일 한 번)" | Out-Null

Write-Host "작업 '$TaskName' 등록 완료 (매일 $($At -join ', ') + 로그인 시 따라잡기, 실패하면 5·15·45분 뒤 재시도, 로그인 중에만, 창 숨김)."
Write-Host "로그: $dir\state\sync.log"
Write-Host "지금 한 번 실행해 보기:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "해제:                    powershell -ExecutionPolicy Bypass -File .\register-task.ps1 -Remove"
