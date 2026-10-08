# C1_Calendar_agent — 서비스 캘린더 (유니버스 공통 기반 C1)

유니버스의 **모든 일정이 모이는 자체 캘린더**. 외부 캘린더와 연동하지 않으므로(전역 결정 G1) 캘린더 자체가 제품의 본체다.
요구사항은 [요구사항정의서.md](../요구사항정의서.md) C1 절, 화면·라우트는 [Frontend-Route.md](../Frontend-Route.md) 3절.

- **`/api/events` 가 여기 있다.** 대시보드 백엔드(`univ_us_local`)는 이 폴더의 라우터를 붙이기만 한다.
- **이 폴더가 저장하는 것은 내 일정·할 일**(`kind: "user"`)뿐이다. 학사(F1)·과제 마감(F6)·수업 회차(F3)는
  각 기능 폴더가 갖고 있고, 백엔드가 소스 함수로 넘겨주면 `/api/events` 에서 **한 배열로 합쳐진다**(C1-R10).
  캘린더에 새로 쓰는 기능이 생기면 `univ_us_local/backend/app/main.py` 의 `CALENDAR_SOURCES` 에 한 줄 더한다.
- **설치할 것이 없다** — 표준 라이브러리 + fastapi(라우터만). 개발 venv(`desktop/sidecar/.venv`)에 더 넣을 것이 없다.
- 내 일정·할 일은 앱 데이터 폴더의 `C1_Calendar_agent/data/univus.db` 에만 있다. 밖으로 나가지 않는다.

```
C1_Calendar_agent/
├── calendar_core/           파이썬 패키지
│   ├── config.py            경로(data/univus.db) · 내 일정 분류 색
│   ├── store.py             SQLite — user_events(일정 + 할 일 한 표) · kv(옛 프로필)
│   ├── service.py           합치는 규칙 — 소스 모으기 · 기간 겹침 · 날짜 검사 (fastapi 를 부르지 않는다)
│   ├── api.py               FastAPI 라우터 build_router(sources) — univ_us_local 이 include
│   └── __main__.py          명령줄
└── data/                    (gitignore, 개발 모드 기본값이 아닐 때만) univus.db — 앱은 앱 데이터 폴더에 둔다
```

> 패키지 이름이 `calendar` 가 아닌 이유: 백엔드가 이 폴더를 `sys.path` 에 넣기 때문에 `calendar/` 로 두면
> **파이썬 표준 라이브러리의 `calendar` 모듈을 가려 버린다**(`http.cookiejar` 등이 쓴다). 그래서 `calendar_core` 다.

## 쓰는 법

앱 대시보드 → 가운데 캘린더. 빈 칸을 클릭·드래그하면 새 일정, 내 일정은 드래그로 옮긴다(C1-R30·R31).
다른 소스에서 온 항목(마감·학사·수업)은 잠겨 있고, 끌면 제자리로 돌아온다.

명령줄 (저장소 루트에서 개발 venv 를 켜고 — `desktop/cli.py` 가 개발 데이터로 `python -m calendar_core` 를 돌린다, `--app` 이면 앱 데이터):

```powershell
python desktop/cli.py calendar_core list                                   # 내 일정·할 일 (--todo · --from · --to)
python desktop/cli.py calendar_core add "스터디" 2026-10-06T19:00 --end 2026-10-06T21:00 --category team --todo
python desktop/cli.py calendar_core done 3                                 # 할 일 완료 토글
python desktop/cli.py calendar_core rm 3
python desktop/cli.py calendar_core count                                  # 건수 · DB 자리
```

명령줄은 **내 일정만** 본다. 캘린더에 함께 뜨는 학사·마감·수업은 각 기능의 명령줄(`cli.py bachelor` · `eclass` · `attendance`)로 본다.

## API

백엔드가 `univ_us_local/backend/app/calendar_events.py` 에서 `build_router(sources)` 로 붙인다.

| 메서드 | 경로 | 내용 |
|---|---|---|
| GET | `/api/events?start&end` | 모든 소스를 합친 목록 (FullCalendar 형식, `extendedProps.kind` = `user`/`deadline`/`academic`/`class`). `start`·`end`(YYYY-MM-DD)를 주면 그 구간에 걸치는 것만 |
| POST | `/api/events` | 내 일정/할 일 추가 `{title, start, end, all_day, category, memo, is_todo, done, origin?}` — `origin='ac:…'` 은 학사 일정 '내 일정에 넣기'(같은 학사 일정이면 409) |
| PATCH | `/api/events/{id}` | 내 일정만. id 가 숫자가 아니면(`dl:`·`ac:`·`cl:`) 404 — 원천이 따로 있다 |
| DELETE | `/api/events/{id}` | 내 일정만 (204) |

`/api/status` 의 `calendar` 칸으로 DB 자리·건수·분류표가 나가고, 화면이 쓰는 `counts`·`categories` 도 여기서 온다.

- 날짜는 tz 없는 로컬 문자열. 종일 일정의 `end` 는 FullCalendar 규칙대로 **exclusive** (9/24~9/25 → `end=2026-09-26`, C1-R14).
- 형식이 틀리거나 종료가 시작보다 빠르면 422, 없는 일정은 404.

## 지키는 선

- 내 일정·할 일은 `data/univus.db` 에만 있다. 외부 캘린더로 내보내지 않고 `.ics` 도 만들지 않는다 (전역 결정 G1).
- `extendedProps.kind` 는 요구사항정의서 C1 3절 표에 등록된 값만 쓴다. 마음대로 늘리지 않는다.
- 소스 하나가 깨져도 캘린더 전체가 죽지 않게, 백엔드의 소스 함수들은 예외를 삼키고 빈 목록을 준다.
- `data/` 는 커밋하지 않는다.

## 옛 자리에서 옮겨 온 것 (2026-09-30)

이 코드는 `univ_us_local/backend/app/`(main.py 의 `/api/events` + `store.py` + `config.py` 의 분류표)에 있었다.
DB 도 `univ_us_local/data/univus.db` 에 있었는데, 서버가 처음 뜰 때 `calendar_core.store.init()` 이 **한 번만**
이 폴더의 `data/` 로 옮긴다. 옛 서버가 파일을 붙잡고 있으면 복사만 하고 알려 주므로, 그 서버를 끄고 다시 켠 뒤
남은 `univ_us_local/data/univus.db` 를 지우면 된다.
