# C2_Profile_agent — 사용자 프로필·학과 마스터 (유니버스 공통 기반 C2)

**한 번 입력한 내 정보를 여러 기능이 같이 쓴다** (전역 결정 G3). 요구사항은 [요구사항정의서.md](../요구사항정의서.md) C2 절, 화면은 [Frontend-Route.md](../Frontend-Route.md) 5절.

| 쓰는 기능 | 무엇에 |
|---|---|
| F1 학사일정 | '내 해당' 판정 — 학년·학적·단과대·학과 |
| F2 졸업요건 | 룰셋 매칭 — 학과·전공 코드·입학년도·이수유형, 평점·취득학점 |
| F3 출결 | 학사경고 안내 — 직전 학기 평점(기준 1.75 미만이면 `/attendance` 에 안내), 시간표 조회 학년 |
| F11 장학 | 자격 판정 — 학년·평점·학점·학자금 지원구간·지역·해당 사항 |

## 설치할 것이 없다

- 프로필 저장·API·학과 목록 수집은 **표준 라이브러리만** 쓴다 → 대시보드 백엔드(`univ_us_local`)가 그대로 붙여 쓴다(`app/student_profile.py`).
- **학사정보시스템에서 가져오기**만 `C3_Login_agent` 의 `.venv`(playwright·bs4)와 로그인 세션을 빌려 쓴다. C3_Login_agent 를 설치하고 한 번 로그인해 두면 된다.

```
C2_Profile_agent/
├── student/                파이썬 패키지
│   ├── schema.py           항목 정의 — 검사 · 쓰는 기능(F1·F2·F11) · 민감정보 이유
│   ├── store.py            SQLite data/profile.db — 항목마다 '자동/내가 입력' 을 남긴다
│   ├── service.py          읽기·쓰기 규칙, 가져오기 반영, 다른 기능용 모양(matching_view), 옛 데이터 옮기기
│   ├── master.py           학과 마스터 읽기·찾기·갱신(옛 코드 보존)
│   ├── master_crawl.py     교육과정검색 수집 (표준 라이브러리)
│   ├── hakstd.py           학사정보시스템 가져오기 (C3_Login_agent .venv 에서 실행)
│   ├── jobs.py             대시보드 버튼 뒤의 백그라운드 작업 (목록 갱신 · 가져오기)
│   ├── notice_bridge.py    F11(notice_agent/data/profile.json)로 넘기기
│   ├── api.py              FastAPI 라우터
│   └── __main__.py         명령줄
├── master/departments.json 학과 목록 스냅숏 (저장소에 포함 — 처음 실행에도 네트워크 없이 뜬다)
├── tests/                  pytest
├── run.cmd
└── data/  state/           (gitignore) 내 프로필 DB · 갱신한 학과 목록 · 가져오기 로그
```

## 쓰는 법

대시보드: 처음 열면 `/onboarding`(학과 → 입학년도·이수유형 → 학사시스템 가져오기), 이후 ⚙ → **내 프로필**.
명령줄 (`run.cmd` = 백엔드 .venv 의 python 으로 `python -m student`):

```powershell
cd C2_Profile_agent
.\run.cmd show                          # 내 프로필 (민감정보는 '입력됨'으로만)
.\run.cmd dept 인공지능                   # 학과 목록에서 코드 찾기
.\run.cmd set-dept 30001265 30001267     # 소속 (학과 코드 [전공 코드])
.\run.cmd set admissionYear=2024 track=single grade=3
.\run.cmd import                         # 학사정보시스템에서 가져오기
.\run.cmd master-sync                    # 교육과정검색에서 학과 목록 다시 받기 (1분 남짓)
.\run.cmd export-notice                  # F11 notice_agent 로 넘기기
.\run.cmd clear                          # 전부 지우기
```

테스트: `..\F1_Bachelor_agent\.venv\Scripts\python -m pytest tests -q` (pytest 가 있는 아무 환경)

## API (대시보드 `/api/docs`)

| 메서드 | 경로 | 내용 |
|---|---|---|
| GET | `/api/profile` | 항목 값 + `filledBy`(자동/입력) + `edited`(자동값을 고침) + `complete`·`missing`(필수 3개) |
| PATCH | `/api/profile` | 보낸 항목만 저장, `null` 이면 지움. 소속은 `{affiliation: {deptCode, majorCode}}` — 학과 목록에 있는 코드만 |
| DELETE | `/api/profile` · `/api/profile/sensitive` | 전부 지우기 · 장학용 민감정보만 지우기 |
| GET | `/api/profile/schema` | 항목 이름 · 쓰는 기능 · 민감정보 이유 · 선택지 |
| POST | `/api/profile/legacy` | 브라우저에만 있던 옛 프로필 옮기기 (프로필이 비어 있을 때만) |
| POST / GET | `/api/profile/import` | 학사정보시스템 가져오기 시작(`{interactive}`) / 진행 상태. 로그인 기록이 없으면 **409 `{needLogin}`** |
| GET | `/api/master/departments` | 학과 선택기 목록 (625곳) |
| POST | `/api/master/departments/sync` · GET `/api/master/status` | 교육과정검색 재수집 · 진행 상태 |

## 규칙

- **소속은 코드로만** (C2-D1): 학과 목록에서 고른 `deptCode`(+`majorCode`)만 받는다. 단과대 코드·이름은 목록에서 붙인다.
- **필수 3개** (C2-D2): 학과·입학년도·이수유형 (단과대는 학과에서 정해진다).
- **이름·학번은 항목이 없다** (C2-D5): 보내면 422. 학사시스템에서도 정규식으로 학년·학적·주전공만 꺼낸다.
- **자동 / 내가 입력** (C2-R05): 항목마다 출처를 남긴다. 다시 가져와도 **내가 입력·수정한 값은 덮지 않는다**(`skipped` 로 알려 줌). 자동값을 고치면 '수정함'.
- **민감정보**(학자금 지원구간·지역·장애/보훈 등, C2-D4·R07)는 선택 입력, 쓰는 이유를 옆에 적고, 한 번에 지울 수 있다. F11 에만 쓴다.
- **바뀌면** F1 의 `updatedAt` 을 올려 화면이 '내 해당'을 다시 받는다 (C2-R08). F1 은 읽을 때마다 프로필로 계산한다.
- 저장은 이 PC 의 `data/profile.db` 뿐 (C2-R11).

## 학과 마스터 (C2-R02·R10)

- 원천: 교육과정검색 `CurriCulumnSM.aspx?aYear=<연도>&aLanguage=1&aColl=<단과대>` — **GET 만으로 학과 select 가 채워진다**(2026-09-28 실측).
  학과·전공 계층은 이름으로 드러난다(`인공지능학부` / `인공지능학부 인공지능전공`).
- 범위: **학부 단과대만**(코드 3000…, 대학원 2000… 제외, C2-Q4 1차 답). 2026학년도 기준 29개 단과대 · 283개 학과 → 선택기 625줄.
  교육과정 DB 에 섞인 비학과 조직(○○사업단·연구센터·부속공장)은 선택기에서 뺀다.
- 한 줄 = 고를 수 있는 한 곳: 학부는 '(전공 배정 전)' 한 줄 + 전공마다 한 줄, 전공 하나뿐인 융합전공은 한 줄.
- 갱신하면 사라진 학과·전공도 지우지 않고 `retired` 로 남긴다 — 옛 코드로 저장된 프로필이 깨지지 않게.
- 요청 간격 1.5초, 동시성 1.

## 학사정보시스템 가져오기 (C2-R04)

C3_Login_agent 의 세션 → 만료면 C3_Login_agent 의 재인증(쿠키 복구 → 저장된 자격증명 무인 로그인) → 그래도 안 되면 '로그인 창 열기'(직접 로그인).
2026-09-28 실측: 학사정보시스템은 로그인 전이면 **자체 로그인 화면(`/Main/Login.aspx`)** 에 머문다 — '내 학사행정 로그인' 버튼을 눌러 SSO 로 넘긴다.
읽는 것: 대시보드(학년·학적·주전공·평점), 기이수성적(취득학점·이수 학기·직전 학기 학점). 값은 로그에 남기지 않고, 결과 파일은 반영 뒤 지운다.
주전공 이름으로 학과 목록에서 소속을 찾아 채운다(전공은 사용자가 고른다). 공식 성적증명과 다를 수 있다.
