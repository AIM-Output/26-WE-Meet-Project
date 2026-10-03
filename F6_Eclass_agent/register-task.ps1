<#
  Windows 작업 스케줄러에 e클래스 자동 수집(F6)을 등록/해제한다.
  정각 기준 N시간마다(기본 4시간: 00·04·08·12·16·20시) + 로그인할 때 run-scheduled.cmd 를 부른다 (F6-R10).
  - 그 시각에 PC 가 꺼져 있었거나 절전이었으면 켜지는 대로 한 번 실행한다(StartWhenAvailable, F6-R11).
    밀린 여러 주기를 몰아서 돌리지 않는다 — tick 이 '가장 최근 정각 이후 실행이 있으면 건너뜀'으로 막는다.
  - 네트워크 오류 재시도(5·15·45분)는 tick 이 직접 한다 → 작업 스케줄러의 재시작 옵션은 쓰지 않는다 (F6-R12).
  "사용자가 로그인되어 있을 때만" 실행 → Windows 비밀번호를 저장할 필요가 없다. 창은 숨김, 출력은 state\sync.log.
  예전 eclass_agent 가 등록한 작업(eClass-Agent-Sync)이 있으면 지운다.

  등록 (주기는 state\settings.json → 없으면 4시간):
      powershell -ExecutionPolicy Bypass -File .\register-task.ps1
  주기 지정 (2·4·6·12 — 대시보드 '수집 원천'에서 바꾸면 이것을 부른다):
      powershell -ExecutionPolicy Bypass -File .\register-task.ps1 -IntervalHours 6
  해제:
      powershell -ExecutionPolicy Bypass -File .\register-task.ps1 -Remove
#>
param(
  [int]$IntervalHours = 0,
  [string]$TaskName = "UnivUs-F6-Eclass-Sync",
  [string[]]$LegacyTaskNames = @("eClass-Agent-Sync"),
  [switch]$Remove
)

$ErrorActionPreference = "Stop"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$stateDir = if ($env:F6_STATE_DIR) { $env:F6_STATE_DIR } else { Join-Path $dir "state" }
$settingsFile = Join-Path $stateDir "settings.json"

foreach ($old in $LegacyTaskNames) {
  if (Get-ScheduledTask -TaskName $old -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $old -Confirm:$false
    Write-Host "예전 작업 '$old' 삭제됨."
  }
}

if ($Remove) {
  if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "작업 '$TaskName' 삭제됨."
  } else {
    Write-Host "작업 '$TaskName' 이(가) 없습니다."
  }
  return
}

# 주기: 인자 → state\settings.json → 4
if ($IntervalHours -eq 0 -and (Test-Path $settingsFile)) {
  try { $IntervalHours = [int]((Get-Content $settingsFile -Raw -Encoding UTF8 | ConvertFrom-Json).intervalHours) } catch { }
}
if (@(2, 4, 6, 12) -notcontains $IntervalHours) { $IntervalHours = 4 }

# 대시보드·명령줄과 같은 값을 보도록 settings.json 에도 적는다
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
$cur = @{}
if (Test-Path $settingsFile) {
  try { (Get-Content $settingsFile -Raw -Encoding UTF8 | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $cur[$_.Name] = $_.Value } } catch { }
}
$cur["intervalHours"] = $IntervalHours
[IO.File]::WriteAllText($settingsFile, ($cur | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))

$runner = Join-Path $dir "run-scheduled.cmd"
if (-not (Test-Path $runner)) { throw "run-scheduled.cmd 를 찾을 수 없습니다: $runner" }

# 창을 띄우지 않도록 숨긴 powershell 로 run-scheduled.cmd 를 호출
$psArg = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command `"& '$runner'`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $psArg -WorkingDirectory $dir

$triggers = @()
$slots = @()
for ($h = 0; $h -lt 24; $h += $IntervalHours) {
  $at = (Get-Date).Date.AddHours($h)
  $triggers += New-ScheduledTaskTrigger -Daily -At $at
  $slots += "{0:00}" -f $h
}
# 로그인할 때도 한 번 (켜 두지 않았던 동안 놓친 주기 따라잡기). 부팅 직후 네트워크 지연을 감안해 2분 지연.
$logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$logon.Delay = "PT2M"
$triggers += $logon

# 놓친 시각은 켜지는 대로(StartWhenAvailable) · 재시도 사슬(최대 5+15+45분)을 감안해 2시간 제한 · 겹치면 새 실행은 무시
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries

# -User + -Settings (LogonType 생략 시 "로그인 중에만 실행", 비밀번호 불필요)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers -Settings $settings -User $env:USERNAME -Force -Description "유니버스 F6 전남대 e클래스 과제·마감·자료 자동 수집" | Out-Null

Write-Host "작업 '$TaskName' 등록 완료 ($IntervalHours 시간마다: $($slots -join '·')시 + 로그인 시, 로그인 중에만, 창 숨김)."
Write-Host "로그: $stateDir\sync.log"
Write-Host "지금 한 번 실행해 보기:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "해제:                    powershell -ExecutionPolicy Bypass -File .\register-task.ps1 -Remove"
