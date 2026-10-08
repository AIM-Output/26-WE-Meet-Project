# F2_Graduation_agent — 졸업요건·학점 트래커 (유니버스 F2)

내가 들은 과목을 자동으로 읽어 **졸업까지 무엇이 얼마나 남았는지**를 영역별로 보여 준다.
요구사항은 [요구사항정의서.md](../요구사항정의서.md) F2 절, 화면·라우트는 [Frontend-Route.md](../Frontend-Route.md) 7절.

> **참고용 · 공식 졸업사정이 아니다.** 최종 확인은 학과 사무실·학사정보시스템에서 한다 (F2-R60 — 모든 화면·명령줄 출력에 붙인다).

- **계산은 규칙 기반 코드 하나**(`graduation/calc.py`)뿐이다. LLM 을 쓰지 않는다 (F2-R29). 가정 계산도 같은 계산기를 한 번 더 돌린다.
- 이수 내역은 학사정보시스템(SSO)에서 **이 PC 에서만** 읽는다. 결과는 `data/graduation.db` 에만 남고, 이름·학번은 읽지 않는다.
- 프로필(학과·전공·입학년도·이수유형·평점)은 **C2_Profile_agent** 의 것을 쓴다 (전역 결정 G3).

```
F2_Graduation_agent/
├── graduation/             파이썬 패키지
│   ├── calc.py             계산기 — 순수 함수 calculate(courses, ruleset, certs, gpa, assumptions) (5절 ①~⑩)
│   ├── rules.py            룰셋 읽기·검사·자동 매칭(C2 6절)·펼치기(과목 목록·대학 공통 조건·내 매핑)
│   ├── curriculum.py       교육과정검색 수집·스냅숏 (학과·전공·입학년도별 교필·전필·전선)
│   ├── store.py            SQLite — 원천(courses)과 내 값(overrides·category_map·certs·rulesets·plans)을 나눈다
│   ├── service.py          화면이 받는 모양 · 과목 추가/구분 지정/제외 · 가져오기 반영 · 룰셋 내 수정본 · 인증 · 내 계획
│   ├── hakstd.py           학사정보시스템 기이수성적 수집 (자식 프로세스 — osenv.module_cmd, 로그인은 C2 의 절차를 빌림)
│   ├── jobs.py             대시보드 버튼 뒤의 백그라운드 작업 (가져오기 · 교육과정 받기)
│   ├── api.py              FastAPI 라우터 (univ_us_local 이 include)
│   └── __main__.py         명령줄
├── rulesets/               기본 룰셋 (저장소에 포함, 값마다 근거)
│   ├── jnu-30001265-2021.json   인공지능학부 2021~2022 입학
│   └── jnu-common-ge-2023.json  전남대 2023학년도 이후 입학 교양 영역 조건 (학과 룰셋에 덧붙는다)
├── curriculum/             교육과정 스냅숏 — 인공지능학부·3개 전공 2021~2026 (네트워크 없이 계산되게)
├── tests/                  pytest 60개 (모의 이수 내역 10건 회귀 · 매칭 · 파서 · 사용자 조작 · 가져오기 배관)
└── data/  state/           (gitignore) 내 이수 내역 DB · 내려받은 교육과정 · 가져오기 로그
```

## 쓰는 법

**설치할 것이 없다.** 앱 대시보드 → 기능 타일 **졸업요건** → `이수 내역 가져오기`.
학사정보시스템 로그인은 C3_Login_agent 의 세션을 빌린다(앱에서 한 번 `로그인 창 열기`로 로그인해 두면 된다). 세션이 없으면 화면에 `로그인 창 열기`가 뜬다.

명령줄 (저장소 루트에서 개발 venv 를 켜고 — `desktop/cli.py` 가 개발 데이터로 `python -m graduation` 를 돌린다, `--app` 이면 앱 데이터):

```bash
python desktop/cli.py graduation status                 # 졸업까지 남은 학점 · 영역별 · 세부 요건 · 인증 · 판정 근거
python desktop/cli.py graduation courses                # 이수 과목 (영역 · 계산 제외 이유)
python desktop/cli.py graduation import                 # 학사정보시스템 기이수성적 가져오기 (--interactive 면 로그인 창)
python desktop/cli.py graduation curriculum             # 내 학과·전공·입학년도 교육과정 받기
python desktop/cli.py graduation rulesets               # 기본 룰셋 목록
python desktop/cli.py graduation add "편입 인정 학점" 30 --area free --year 2024 --semester 1
python desktop/cli.py graduation clear                  # 이수 내역·내 지정·수정본·계획 전부 지우기
```

테스트: 이 폴더에서 `python -m pytest tests -q` (개발 venv `desktop/sidecar/.venv`)

## 계산 규칙 (요구사항정의서 F2 5절)

| 단계 | 규칙 |
|---|---|
| ① 유효 과목 | 성적 F·NP·U·W 제외, 교과목상태에 포기·취소·철회 제외, 사용자가 뺀 과목 제외 |
| ② 재수강 | 같은 학수번호(없으면 과목명+학점)는 **성적이 가장 높은 1건**만. 같은 학기 두 줄이면 '두 번 들어 있음' |
| ③ 영역 | 사용자 지정 > 교과구분 매핑(기본 + 내 지정). 못 하면 **미분류** → 판정 '확인 필요' + 배너 |
| ④⑤ 합산·이월 | 영역별 합, 초과분은 `overflowTo` 로 **한 번만**(연쇄 없음) — 교필→교선, 전필→전선, 교선·전선→일반선택 |
| ⑥ 부족 | `max(0, 기준 − 취득)`. 전공필수·교양필수는 **과목 단위**로 남은 과목(학수번호, 없으면 이름)도 |
| ⑦ 총계 | 유효 과목 학점 합(영역과 무관). '더 들어야 할 학점' = max(총 부족, 영역 부족 합) |
| ⑧ 평점 | 학사시스템 평점 그대로 비교. 만점 척도가 다르면 비교하지 않는다 |
| ⑨ 인증 | 사용자 체크(충족/미충족/모름). 이수 과목에서 관련 과목(생활영어1 등)을 찾으면 **힌트만** 준다 |
| ⑩ 판정 | 기준이 불확실(인접 연도·미분류·과목 목록 없음) → **확인 필요** / 부족 → **부족** / 모르는 것 → **확인 필요** / 전부 → **충족**. 이유 목록을 같이 준다 |

## 기본 룰셋과 근거

| 조각 | 원천 (2026-09-28 확인) | 값 |
|---|---|---|
| 졸업소요학점 | [인공지능학부 졸업안내](https://aisw.jnu.ac.kr/aisw/515/subview.do) '졸업소요학점' 표 (적용년도 **2021-2022**) | 졸업 140 · 교양필수 18 · 교양선택 18 · 전공필수 15 · 전공선택 33 (전공기본과정 48) |
| 졸업인증 | 같은 페이지 '졸업자격인정기준' | 졸업논문(전공프로젝트) · 외국어(회화 포함 영어 교과목 / 생활영어1·2 / TOEIC 600) |
| 과목 목록 | 교육과정검색 GET (`aYear·aColl·aDept`) | 전필 = 학부 4(자료구조·JAVA·인공지능·알고리즘) + 전공 캡스톤 1 = **15학점**, 교필 6과목 = **18학점** — 표의 학점과 맞는다 |
| 교양 영역 (2023~ 입학) | [교육혁신본부 교양 이수 및 편성](https://ile.jnu.ac.kr/ko/liberal/organize) | 역량교양 창의·감성·공동체 각 3 · 기초SW 3 · 표현과소통 3 · 진로와창업 2 · 인문학 8(넉넉히 세므로 채워도 '확인 필요') |
| 전공심화·복수·부전공 | [전남대 교육과정 안내](https://www.jnu.ac.kr/MainUniLife/Curriculum/Curriculum) | 심화(+21)는 선택 — 메모로만. 복수·부전공은 1차 범위 밖(단일전공 기준 + 경고) |

- **학과 홈페이지에 2023학년도 이후 행이 없다** → 2023~ 입학생은 C2 6절 ③ '가장 가까운 이전 연도'(2021~2022)로 계산하고 경고 + '확인 필요'.
  학과에 확인한 뒤 `/settings/requirements` 에서 **저장하면 내 수정본**이 되어 경고가 사라진다.
- **최저 졸업 평점은 찾지 못해 비워 두었다** (`minGpa: null` — 판정에 걸지 않는다). 교학규정에서 확인되면 넣는다.
- 다른 학과는 룰셋이 없다 → 화면에서 빈 템플릿을 채우거나 '비슷한 학과에서 복사'. 과목 목록은 `교육과정 받기`로 그 학과 것을 받는다.
- 새 기본 룰셋을 더하려면 `rulesets/` 에 JSON 을 넣는다(`id` · `deptCode`/`majorCode` · `admissionYear`~`admissionYearTo` · `track` · 값마다 `evidence`). 파일 형식은 `rules.py` 머리 주석.

## 학사정보시스템 기이수성적 (F2-R01·R02·R03)

`/web/Sung/Sung010` [조회] → `table#…gvData` (년도 · 학기 · 교과구분 · 교과목번호 · 교과목명 · 성적 · 학점 · 교과목상태 · 재이수 · 교양영역).
합계 행('학기 평점')은 4자리 연도가 아니라서 뺀다. 학기 '하계 계절'·'동계 계절'은 여름·겨울로.
로그인은 C2 의 `student.hakstd.hakstd_page` 를 그대로 쓴다(로그인 전이면 `/Main/Login.aspx` 에 머무는 함정 포함). 같은 김에 대시보드의 평점·학년을 읽어 C2 프로필에 **자동**으로 넣는다(내가 입력한 값은 C2 가 덮지 않는다).
결과 파일(성적)은 저장 뒤 바로 지우고, 로그에는 과목 수·학기 수만 남긴다. 표를 못 읽으면(형식 변경 의심) **이전 이수 내역을 그대로 둔다**.

## 대시보드와 잇는 법

`univ_us_local/backend/app/graduation.py` 가 이 폴더를 `sys.path` 에 넣고 `graduation.api.build_router(get_profile, on_profile=…)` 를 include 한다.
`/api/status` 의 `graduation` 칸(남은 학점·판정·한 줄 요약·updatedAt)이 기능 타일을 채우고, 프로필이 바뀌면 `updatedAt` 을 올려 화면이 다시 부른다(C2-R08).
폴더 위치가 다르면 백엔드에 환경변수 `F2_AGENT_DIR` 을 준다.

## API (대시보드 `/api/docs`)

| 메서드 | 경로 | 내용 |
|---|---|---|
| GET | `/api/graduation/status?track=` | 판정 · 총계 · 영역별(포함 과목·남은 과목) · 세부 요건 · 인증 · 미분류 · 이수 과목 · 기준(매칭 단계·경고·근거) |
| GET | `/api/graduation/summary` | 타일용 한 줄 |
| POST / PATCH / DELETE | `/api/graduation/courses[/{id}]` | 직접 입력 추가 · 구분 지정(`applyToCategory`면 그 교과구분 전체) · 계산 제외 · 직접 입력만 삭제. 응답에 다시 계산한 status |
| POST / GET | `/api/graduation/sync` | 기이수성적 가져오기 `{interactive}` — 로그인 기록이 없으면 **409 `{needLogin}`** / 진행 상태 |
| POST | `/api/graduation/simulate` | 가정 `{track, assumptions: {areas, courses}}` → 현재 / 가정 후 |
| GET / PUT / DELETE | `/api/graduation/ruleset?year&track` | 매칭 결과 + 펼친 룰셋 + 편집용 원본(없으면 빈 템플릿) / 내 수정본 저장 / 기본값으로 되돌리기 |
| GET | `/api/graduation/rulesets[/{id}]` | 기본 룰셋 목록 · 하나 ('비슷한 학과에서 복사') |
| GET / PUT | `/api/graduation/categories` | 교과구분 → 영역 매핑 (기본 + 내 지정 + 내 과목에 나온 구분) |
| PATCH | `/api/graduation/certifications/{key}` | `{state: done|todo|unknown, memo}` |
| GET / POST / DELETE | `/api/graduation/plans[/{id}]` | 가정 '내 계획' |
| GET / POST | `/api/graduation/curriculum[/sync]` | 내 학과·전공·입학년도 교육과정 스냅숏 유무 / 받기 |

## 지키는 선

계산 경로에 LLM 없음 · 이수 내역·평점은 이 PC 의 SQLite 에만 · 이름·학번 미수집 · 교육과정검색 요청 간격 1.5초·동시성 1 · `data/` `state/` 공유 금지.
