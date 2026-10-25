# F11_Scholarship_agent — 장학 공지 매칭·신청서 초안 (유니버스 F11)

전남대 안에서 장학 공지가 올라오는 곳(학교 전체 · 부서·센터 · 사업단 · **내 단과대학·학과**)을 모아, C2 프로필과 **조건별로 대조**하고
(해당 / 확인 필요 / 비해당 / 마감 / 대상 아님), 신청서 초안·제출 서류 체크리스트·신청 링크까지 만들어 둔다.
**제출은 하지 않는다.** 확인한 뒤 본인이 직접 신청한다.

요구사항: [요구사항정의서.md](../요구사항정의서.md) F11 절(12절 구현 메모) · 화면: [Frontend-Route.md](../Frontend-Route.md) 16절 — `/scholarships`
참고 코드였던 [notice_agent](../notice_agent/README.md) 의 규칙 추출·판정·초안 골격을 옮겨 와 앱 기능으로 다시 짰다.

```
F11_Scholarship_agent/
├── directory/sources.json   전남대 장학 원천 목록(2026-10-09 실측) — 게시판 주소·말머리·대상(관련 단과대학·학과·계열)·근거
├── scholarship/
│   ├── config.py            경로(F11_DATA_DIR·F11_STATE_DIR) · 요청 간격 1.5초 · 판정 문턱 0.6 · 수집 시각 06·18시 · LLM 슬롯
│   ├── registry.py          원천 목록 + 프로필 → 내 장학 원천(관련 여부·켜짐) · 작성 부서 → 사업단 · 학과 홈페이지(F1 목록)
│   ├── extract.py           공지 → 자격 요건(근거 한 줄씩) — 학년·학기·평점·학점·소득구간·학적·기간·서류·방법 + 지역·계열·단과대학·캠퍼스·대상 집단
│   ├── regions.py           지역 장학 판정용 시·군·구 → 시·도 사전 (2026 행정구역)
│   ├── match.py             요건 × 프로필 → 판정 + 조건별 근거 (민감정보가 모자라면 sensitive 표시 → 화면이 그 자리에서 묻는다)
│   ├── store.py             SQLite(data/scholarship.db) — 공지 · 사용자 상태(판정 뒤집기·진행 상태) · 초안 · 원천 · meta
│   ├── service.py           화면 모양 — 목록·상세·이력·원천·초안 재료·캘린더·할 일 · 타일·브리핑
│   ├── draft.py · llm.py    신청서 초안 7단 구성 · LLM(선택, OpenAI 호환)
│   ├── basicinfo.py         초안 기본 정보(이름·학번·소속·학년·연락처·이메일 + 작성일) — 재료에만 두고 LLM 에는 안 보낸다 (F12 도 쓴다)
│   ├── notify.py            새 해당·확인 필요 즉시 · 마감 D-3·D-1 (알림 센터 = F1 notifications)
│   ├── runner.py            '지금 수집' · 앱이 떠 있을 때 06·18시 자동 수집 (자식 프로세스)
│   ├── collect.py           수집 파이프라인 (자식 프로세스에서만 — requests·bs4·pypdf)
│   ├── attachments.py       첨부 PDF·HWP·HWPX·DOCX 글자 + 이미지 OCR (파일은 저장하지 않는다 — F12 도 이것을 쓴다)
│   ├── sources/             게시판 수집기 — aspx(대표 공지·국제협력·언어교육원) · k2web(+학과 게시판 찾기) · coss(+말머리) · coss_apply ·
│   │                        coursemos · kboard(sojoong.kr) · xe(startup.jnu.ac.kr) · events(CNU Events) · catalog
│   ├── api.py               FastAPI 라우터 /api/scholarships*
│   └── __main__.py          명령줄
└── tests/                   90개 — 학교 사이트에 접속하지 않는다 (HTML 조각·손으로 넣은 공지·손으로 만든 HWP 레코드·가짜 OCR)
```

## 첨부·이미지 읽기 (`attachments.py`, 2026-10-25)

| 형식 | 읽는 법 |
|---|---|
| PDF | pypdf 앞 15쪽. 글자가 없는 스캔 PDF 는 OCR(앞 3쪽, Windows 만) |
| HWPX · DOCX | zip 안의 XML |
| **HWP 5.0** | `olefile` 로 `BodyText/Section*` 를 열어(zlib) 문단 글자 레코드만 — **표는 한 행을 `칸 \| 칸` 한 줄로**(기간 규칙이 한 줄을 본다). 배포용·암호 문서는 미리보기 글자(`PrvText`)만, 그림만 든 HWP 는 `BinData` 의 그림을 OCR |
| 본문 이미지 · JPG·PNG 첨부 | 본문(+읽은 첨부 글자)이 300자 미만일 때만 OCR, 공지 하나에 4장까지 |
| 엑셀·PPT·zip | 못 읽는다 → '첨부를 읽지 못했습니다' + 확인 필요 |

**OCR 은 OS 내장 엔진**(C0 `osenv/ocr.py`) — Windows 는 `Windows.Media.Ocr`(PowerShell 5.1 이 `osenv/ocr_win.ps1` 을 돌린다, 설치 없음), macOS 는 Vision(pyobjc, 사이드카 requirements 에 맥만). 모델을 앱에 묶지 않는다. 이 컴퓨터에 한국어 OCR 이 없으면 OCR 없이 예전처럼(`OCR 필요`). 수집 로그 첫머리에 `OCR: windows (ko)` 또는 `OCR 없음 — 이유` 가 찍힌다. `UNIVUS_OCR=off` 로 끈다(테스트는 끈다).

- OCR 로 읽은 글자는 `attach_text` 에 `[본문 이미지 OCR]` · `[첨부 OCR: 이름]` 머리를 달아 둔다 → 추출이 `ocr: true` 로 표시, **신뢰도 상한 0.55**, 미달이 있어도 '비해당' 대신 **확인 필요**(OCR 은 '3.5' 를 '3.0' 으로 읽기도 한다). 상세 화면에 '이미지에서 읽은 글자'.
- OCR 글자 다듬기: 표 이미지는 이름표와 값이 다른 줄로 나온다 → `제출기한` + `2026. 11. 11.(수)` 를 한 줄로. 장식을 잘못 읽은 한 글자 줄은 버린다. '신정기간' → '신청기간'(자주 틀리는 것만).
- 읽는 법의 판 `notices.reader_ver`(1 예전 · 2 +HWP · 3 +OCR). 판이 낮고 다시 읽으면 나아질 공지(본문 이미지 · 못 읽은 HWP·PDF·이미지 첨부)는 원천마다 `REREAD_MAX`(6)건씩 상세를 다시 받는다 — 업데이트 뒤 며칠에 걸쳐 예전 공지가 채워진다.
- 실측(2026-10-25): HWP 첨부 6개 중 5개 읽음(1개는 그림만 → OCR). 공문·표 포스터는 평점·기간까지 맞게, 장식 글꼴 포스터는 군데군데 깨진다. 공지당 1~7초.

## 원천 목록 — 왜 이 곳들인가 (2026-10-09 실측)

조사: 대표 홈페이지 '교내홈페이지' 목록 · 산학협력단 '사업단 현황' 표 · 대표 공지사항의 작성 부서(전체 240건 / 장학안내 160건) · 각 사이트 게시판을 직접 열어 구조 확인.
**2026-10-25 다시 조사**(사용자 요청 — SW중심대학 sojoong.kr 처럼 빠진 사업단 사이트): 대표 공지 30쪽(600건)의 작성 부서 중 사업단·센터 글을 열어 본문 속 링크 확인 · 산학협력단 '사업단/센터' 표(60곳, 대부분 연구센터) · 사업단 이름으로 짐작한 `*.jnu.ac.kr` 주소 DNS 확인 후 첫 화면 열기. 새로 찾은 것: sojoong.kr · futurecar.kr · jnu.nccoss.kr 프로그램 신청 · startup.jnu.ac.kr · events.jnu.ac.kr · lec·counsel · 산학협력단 공지. 학교 밖에서 안 열리거나(ris·security·ai.jnu.ac.kr) 403(linc)이거나 사이트가 없는 사업단은 계속 작성 부서로 받는다. glocal.jnu.ac.kr(글로컬대학)은 보도자료 게시판뿐이라 넣지 않았다.

| 묶음 | 원천 (`key`) | 읽는 곳 | 기본으로 켜는 사람 |
|---|---|---|---|
| 학교 전체 | 장학안내 (`jnu_scholarship`) | www.jnu.ac.kr 공지 `cate=8` — 학생과가 올리는 국가·교내·교외 재단·지자체 장학 (장학 글의 98%) | 모두 |
| | 전체 공지 (`jnu_notice`) | 같은 게시판의 다른 분류 — 사업단·단과대학·여수 교학과가 모집공고 분류로 올리는 장학 (제목 어휘로 거름) | 모두 |
| | 상시 장학 안내 (`jnu_catalog`) | 대표 홈페이지 '교내·교외 장학금' 표 — 주 1회 (학부 40개, 대학원 표 제외) | 모두 |
| | CNU Events (`jnu_events`) · 2026-10-25 | events.jnu.ac.kr 행사일정 — 학교 전체의 특강·세미나·박람회·현장실습 모집 (`events`) | 모두 |
| 부서·센터 | 국제협력본부 (`international`) · 언어교육원 (`lec`, 2026-10-25) | international.jnu.ac.kr `BoardID=3` · lec.jnu.ac.kr 강좌소식 `BoardID=2` (같은 aspx 게시판) | 모두 |
| | 교육혁신본부 (`ile`) · 성장마루 (`grow`) | coursemos `/ko/division·learning/notice` · `/ko/info/notice` | 모두 |
| | 발전기금재단 (`fund`) · 총동창회 (`alumni`) · 장애학생지원센터 (`support`) · 학생생활상담센터 (`counsel`, 2026-10-25) | K2Web 공지 (제목 어휘로 거름, 동창회는 '장학생·선발·모집' 글만) · `counsel/2012` | 모두 |
| | 공학교육혁신센터 (`icee`) | K2Web `icee/2798` | 공과대학·공학대학·AI융합대학 |
| | 취업진로포털 (`capd`) · 학군단 (`rotc`) · 광주국제개발협력센터 (`idcc`) | **게시판이 로그인 필요 / 목록을 서버에서 안 그림 / 블로그** → 학교 공지(작성 부서)·상시 안내로 받는다 (`relay`) | 모두 |
| 사업단 | AICOSS (`aicoss`) · 차세대통신 COSS (`nccoss`) · 차세대통신 프로그램 신청 (`nccoss_apply`) | `aicoss.kr` **말머리 `cate=전남대학교`만**(7개 대학 연합 게시판, 2026-10-25) · `jnu.nccoss.kr` `/www/notice/` · `/www/apply_program/`(신청 기간·진행 기간·상태, `coss_apply`) | AI·SW·전자·통신 계열 |
| | 이차전지특성화 (`battery`) · 그린바이오 COSS (`greenbio`) | K2Web `battery/3351` · `greenbio/3467` | 소재·화학·에너지 / 농생대·생명 |
| | SW중심대학 (`sojoong`) · 정보보호특성화 (`aisw_sec`) | **sojoong.kr 자체 사이트**(워드프레스 KBoard, `kboard`, 2026-10-25 — 전에는 인공지능학부 말머리 239) · 인공지능학부 게시판 말머리 `536`(security.jnu.ac.kr 은 학교 밖에서 안 열림) | AI·SW 계열 |
| | 미래차 부트캠프 (`futurecar`) | futurecar.kr `/notice/` (AICOSS 와 같은 CMS, 경로만 다름) | 기계·전기·전자·모빌리티·AI (전공 무관 참여) |
| | 창업중심대학 (`startuphub`) · 전남 RISE 앵커 (`rise_jn`) | K2Web `startuphub/3636` · `rise/3734` | 모두 / 여수캠퍼스 |
| | 창업보육센터·창업포털 (`startup_center`) | startup.jnu.ac.kr `board_MRLV57` (XpressEngine, `xe` — https 인증서 이름이 달라 http) — 실험실 창업 아카데미·메이커톤 | 모두 |
| | 산학협력단 공지 (`sanhak`) | sanhak.jnu.ac.kr K2Web `sanhak/1151` — 광주 RISE·앵커·공유대학 사업단이 올림(대부분 채용·연구 행정) | 모두 |
| | 반도체특성화 · HUSS · 광주전남 RIS · 광주 RISE · LINC · AI 부트캠프 · 이공계기초역량 · 창업교육혁신선도대학 | 자체 게시판을 못 찾았거나 막혀 있다(2026-10-25 다시 확인: ris·security 는 학교 밖에서 안 열림, linc 403, 나머지는 사이트 없음) → 학교 공지의 **작성 부서**(`writers`)로 알아본다 (`relay`) | 관련 학과 |
| 내 소속 | 내 단과대학 (`my_college`) · 내 학부(과) (`my_dept`) | 프로필 소속 → F1 홈페이지 목록(`F1_Bachelor_agent/directory/homepages.json`) → **'장학' 메뉴 > 공지 게시판의 '장학' 말머리 > 공지 전체 + 제목 어휘** (7일마다 다시 찾기) | 프로필이 있으면 |

관련 사업단이 아니어도 융합전공·마이크로디그리처럼 **누구나 참여할 수 있는 곳**은 '전공 무관 참여'로 보여 주고 사용자가 켤 수 있다. 사용자가 켜고 끈 것이 기본값을 이긴다.
사이트가 개편되면 `directory/sources.json` 과 `scholarship/sources/` 의 해당 수집기를 같이 고친다. 확인은 `sync --dry-run --source <key>`.

**F12 대외활동이 이 원천 목록과 `scholarship/sources/` 수집기를 그대로 import 해서 쓴다**(2026-10-10) — 장학 어휘가 걸린 글은 여기, 나머지는 F12. 수집기를 고치면 F12 도 같이 바뀐다(`F12_Activity_agent` 테스트도 돌릴 것). 두 수집은 서로의 `state/sync.lock` 을 기다려 같은 서버를 동시에 읽지 않는다.

## 판정 규칙 (요구사항정의서 F11 5절)

- 조건마다 **충족 / 미달 / 모름** + 근거(원문 한 줄). 프로필에 없는 값은 '모름'이지 '미달'이 아니다.
- 평점 척도가 다르면(4.5 vs 4.3) 환산하지 않고 모름. 백분위(100점) 요건도 모름.
- 추출 신뢰도 < 0.6 이면 결과가 어떻든 확인 필요. 규칙만으로 0.8 까지(조건을 많이 읽고 신청 기간까지 읽었을 때). 본문이 이미지인데 OCR 도 못 했으면 0, 못 읽은 첨부만 있고 본문이 짧으면 0.4 상한, OCR 로 읽었으면 0.55 상한(미달도 확인 필요로).
- **지역 장학**: 시·도가 다르면 미달 / 같고 공지가 시·군 단위면 모름 / 시·도 단위면 충족. 거주지만 다르고 출신 고교를 모르면 미달로 단정하지 않고 출신 고교 지역을 묻는다(본문이 '주소'만 말하면 거주지로 단정).
- **확실한 미달**(제목의 [지역 재단]·단과대학·캠퍼스·대상 집단)은 본문을 못 읽어도 비해당.
- 대상 아님: 선발 결과·명단 · 홍보·캠페인·박람회 · 대학원생 전용 · 외국인 유학생 전용.
- 사용자가 뒤집은 판정이 이긴다(근거는 그대로, 미달이 있으면 초안 위에 경고). 프로필이 바뀌면 다음 호출부터 바로 재판정(판정은 저장하지 않는다).

## 명령줄 (개발 venv — `desktop/sidecar/.venv`)

```
python desktop/cli.py scholarship sync --dry-run              # 어떤 글이 잡히는지만 (저장 안 함)
python desktop/cli.py scholarship sync --source jnu_scholarship
python desktop/cli.py scholarship sources                     # 원천 · 관련 여부 · 켜짐 · 마지막 수집
python desktop/cli.py scholarship list [--all] [--json]       # 판정 목록 (프로필은 C2 에서)
python desktop/cli.py scholarship show www:70498              # 조건별 근거 · 추출값
python desktop/cli.py scholarship catalog                     # 상시 장학 안내만 다시
```

`--college · --dept · --major` 를 붙이면 그 소속으로 바꿔 본다(다른 학과 학생이 어떤 원천을 받는지 확인할 때).

## API (`/api/scholarships*`)

| | |
|---|---|
| `GET /api/scholarships` | 목록 · 건수 · 수집 상태 · 프로필 요약 |
| `GET·PATCH /api/scholarships/items/{id}` | 상세 / 판정 뒤집기 `{verdict, reason}` · 진행 상태 `{progress, note, amount}` |
| `POST·PUT·DELETE /api/scholarships/items/{id}/draft` | 초안 만들기 `{borrowFrom?}`(재료 없으면 409) · 고치기 · 지우기 |
| `POST /api/scholarships/items/{id}/calendar` · `/todos` | 마감 → C1 내 일정 · 서류 → 할 일 (출처 `sch:<id>`) |
| `GET /api/scholarships/history` | 학기별 신청·선정·금액 |
| `GET /api/scholarships/sources` · `PATCH …/sources/{key}` | 원천 · 켜고 끄기 (`null` = 기본값) |
| `POST /api/scholarships/sync` | 지금 수집 |
| `GET·PUT·DELETE /api/scholarships/materials` | 초안 재료 (프로필과 따로) — `basic{name, studentId, department, grade, phone, email}` + 진로·활동·형편·강조점. 기본 정보 빈 칸은 대외활동 재료의 기본 정보 → 프로필 소속·학년으로 미리 채운다(`basicFrom`) |

`/api/status` 의 `scholarship` 칸(타일 숫자)을 부를 때 새 장학 알림 배달과 06·18시 자동 수집 확인도 같이 한다.

## 테스트

```
cd F11_Scholarship_agent
..\desktop\sidecar\.venv\Scripts\python -m pytest tests -q        (맥: ../desktop/sidecar/.venv/bin/python)
```

## 지키는 선

- 요청 간격 1.5초 · 동시성 1 · 공개 게시판만 (로그인이 필요한 게시판은 읽지 않는다 — 취업진로포털처럼).
- 첨부·이미지 파일은 저장하지 않는다(글자만 — OCR 도 메모리에서, PowerShell 에는 표준입력으로 넘긴다). 이름·학번은 수집·프로필·LLM 프롬프트 어디에도 넣지 않는다 — 사용자가 초안 재료의 **기본 정보**에 적은 것만(2026-10-25 사용자 결정) 이 PC 에서 초안에 채운다(LLM 이 남긴 `{{이름}}` 빈칸까지). '재료 지우기'로 같이 지워진다.
- 민감정보(소득구간·거주 지역·출신 고교·해당 사항)는 C2 프로필에만, 판정에만 쓰고 PC 밖으로 나가지 않는다.
- 제출은 하지 않는다. 어떤 신청 버튼도 누르지 않는다.
- `data/`·`state/` 는 공유하지 않는다 (`.gitignore`).
