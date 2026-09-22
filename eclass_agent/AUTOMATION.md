# 백그라운드 자동 수집 (완전 무인)

최초 1회 로그인 후, 스케줄러가 창 없이 주기적으로 자동 로그인 → 수집한다.

## 인증이 어떻게 유지되나 (실측 2026-09-14)

이 PC 는 최근 로그인 때 **신뢰 기기로 등록**되어 있다. 그래서:

| 요소 | 수명 | 의미 |
|---|---|---|
| `RathonSSO_TrustDevice_*` (신뢰 기기) | **약 1년** | 아이디/비밀번호로 로그인해도 **휴대폰 2차 인증이 생략**된다 |
| Moodle / SSO 세션 | 유휴 몇 시간 | 살아있으면 쿠키만으로 바로 접속·복구 |

→ 세션이 죽어도, 저장된 자격증명으로 headless 로그인 → 신뢰 기기라 2차 인증 없이 통과 → **사람 개입 0.**
검증됨: 죽은 세션에서 `login.py --auto` 가 2차 인증 없이 로그인 성공, 스케줄 작업이 `deadlines.md` 자동 갱신.

**중요한 흐름**: 반드시 `lms_sso.php`(SSO 시작점) → 'SSO 로그인' → `idpm.jnu.ac.kr` 경유로 가야
신뢰 기기 쿠키가 확인된다. 전체 세션(state)을 그대로 써야 하며, 쿠키를 골라내면 신뢰 인식이 깨진다.

### 신뢰 기기가 만료되면 (약 1년 뒤, 또는 학교가 재인증 요구 시)

스케줄 실행이 2차 인증에서 막혀 `exit 2` 로 조용히 건너뛰고 `state\login_debug.png` 를 남긴다.
그때 `login.cmd` 를 한 번 수동 실행해 휴대폰 2차 인증을 통과하면(아이디/비번은 자동 입력됨)
신뢰 기기가 갱신되어 다시 1년간 무인으로 돌아간다.

---

## 설정 (이미 완료됨)

```powershell
cd <프로젝트 폴더>\eclass_agent
.\login.cmd           # 1) 대화형 로그인 — 2차 인증 통과 + 신뢰 기기 등록 (state 저장)
.\setup-creds.cmd     # 2) 아이디/비밀번호 저장 (화면에 안 보임, DPAPI 암호화)
.\login.cmd --auto    # 3) 무인 로그인 검증 → "성공. 세션 저장됨."
```

### 스케줄 등록

```powershell
powershell -ExecutionPolicy Bypass -File .\register-task.ps1 -IntervalHours 4
```

- 로그인되어 있을 때만 실행 → **Windows 비밀번호는 저장하지 않음**, 창도 안 뜸
- 로그: `state\sync.log`
- 즉시 한 번: `Start-ScheduledTask -TaskName eClass-Agent-Sync`
- 상태: `Get-ScheduledTaskInfo -TaskName eClass-Agent-Sync`  (LastTaskResult 0 = 성공)
- 해제: `powershell -ExecutionPolicy Bypass -File .\register-task.ps1 -Remove`
- 간격 변경: 같은 명령을 `-IntervalHours 2` 등으로 다시 실행(-Force 로 덮어씀)

> 폴더를 옮기거나 이름을 바꾸면 스케줄 작업이 옛 경로를 가리켜 실패한다(`0x8007010B`).
> 그럴 땐 새 위치에서 `register-task.ps1` 을 다시 실행하면 경로가 갱신된다.

### 동작 순서 (sync 실행 시)

1. 저장된 세션으로 바로 접속 (살아있으면 그대로 수집)
2. 죽었으면 → SSO 쿠키로 조용히 복구 (`refresh_via_sso`)
3. 그래도 안 되면 → 저장된 자격증명으로 headless 자동 로그인 (신뢰 기기라 2차 인증 생략)
4. 신뢰 기기까지 만료됐으면 → `exit 2`, 로그·스크린샷 남기고 다음 수동 로그인 때 재개

### 겹쳐 실행되면

대시보드(`univ_us_local`)의 "e클래스 동기화" 버튼도 같은 `run-sync.cmd` 를 부른다. `sync.py` 가 `state\sync.lock` 으로
서로를 확인하므로 예약 실행과 버튼이 겹쳐도 뒤의 것이 `exit 3` 으로 물러나고 로그에 "이미 실행 중" 한 줄만 남는다.
반대로 예약 실행이 도는 동안에는 대시보드가 "예약 동기화 진행 중…" 으로 보여 주고 끝나면 결과(`state\sync.last.json`)를 읽는다.

> 작업 스케줄러의 `LastTaskResult` 는 `powershell -Command` 래퍼 때문에 0 아니면 **1** 로만 보인다 (2·3 구분 없음).
> 실제 종료 코드는 `state\sync.last.json` 의 `exit_code` 를 본다.

---

## 보안 트레이드오프

- 비밀번호는 **암호화된 형태로만** 이 PC에 존재(평문은 파일·로그 어디에도 없음).
  DPAPI CurrentUser 범위라 **이 Windows 계정에서만** 복호화된다. 학교 비번을 바꾸면 `setup-creds.cmd` 재실행.
- 무인을 끄려면 `.\setup-creds.cmd --clear`. 그러면 세션이 죽었을 때 자동 로그인 대신 수동 `login.cmd` 가 필요해진다(반자동).
- 신뢰 기기 등록은 이 PC 한정이다. 다른 PC 에서는 처음에 휴대폰 2차 인증을 다시 거쳐야 신뢰 기기가 된다.
