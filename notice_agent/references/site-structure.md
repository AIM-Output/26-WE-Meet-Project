# 전남대 장학 공지 소스 — 사이트 구조 (2026-09-13 실측)

수집기가 의존하는 URL 규칙·셀렉터를 적어 둔다. 사이트가 개편되면 **이 문서와 `scripts/sources/`의 해당 파일을 같이** 고친다.
확인 방법: `run.cmd collect --dry-run --source <key>` 로 목록이 잡히는지 → 안 잡히면 여기 셀렉터부터 대조.

| # | 소스 key | 사이트 | 수집기 kind | 로그인 | 비고 |
|---|---|---|---|---|---|
| 1 | `jnu_home_scholarship` | www.jnu.ac.kr 공지사항 › 장학안내 | `jnu_aspx` | 불필요 | 학생과가 올리는 교내·교외·국가 장학 전부. **주 소스** |
| 2 | `aisw_dept`, `cvg_college` | aisw.jnu.ac.kr(인공지능학부), cvg.jnu.ac.kr(AI융합대학) | `k2web` | 불필요 | 학과·단과대 자체 장학(동창장학회 등). 학과가 다르면 site/board 만 교체 |
| 3 | `aicoss` | aicoss.kr 인공지능혁신융합대학사업단 | `aicoss` | 불필요 | 사업단 근로장학·성과장학 |
| 4 | `hakstd_catalog` | hakstd.jnu.ac.kr 학사정보시스템 › 장학 | `hakstd` | **SSO** | 교내·법정·교외 장학 **카탈로그**(지원대상·성적기준 전문) + 신청 메뉴 |
| 5 | `international` | international.jnu.ac.kr 국제협력과 | `jnu_aspx` | 불필요 | 교환학생·외국정부초청 장학 |
| – | 포털 portal.jnu.ac.kr | 위 게시판들을 모아 보여주는 개인화 화면 | (수집 안 함) | SSO | 출처 발견용. 여기서 1·2·5 의 원본 URL 을 얻었다 |

공통 정책: 요청 간격 1.5초, 동시성 1, 목록은 1~2페이지만, 첨부는 PDF/HWP/HWPX/DOCX/XLSX 20MB 이하만.

---

## 1. 전남대 대표 홈페이지 공지사항 (`jnu_aspx`)

- 목록: `https://www.jnu.ac.kr/WebApp/web/HOM/COM/Board/board.aspx?boardID=5&cate=8&page=N`
- `cate` 값 (select#searchCate): `5` 학사안내 · `6` 대학생활 · `7` 취업정보 · **`8` 장학안내** · `9` 행사안내 · `10` 병무 · `13` 채용공고 · `15` 공모전 · `16` 모집공고 · `17` 학술연구
  → F12(맞춤 기회)는 `15`,`16`, F1(학사일정)은 `5` 를 같은 수집기로 받으면 된다.
- 목록 구조: `table.board_list#grvw_board_list tbody tr`
  - `td:nth-child(1) span.label` = "공지"(상단 고정, 매 페이지 반복됨 → id 로 중복 제거)
  - `td.title a[href]` → `board.aspx?boardID=5&bbsMode=view&page=1&key=<글번호>&cate=8` — **글 번호는 `key`**
  - `td:nth-child(3)` 작성자(학생과), `td:nth-child(4)` 작성일 `YYYY-MM-DD`, `td:nth-child(5)` 조회
- 페이지네이션: `div.pagination ul li a[href*="page=N"]`
- 상세: `div.board_view_wrap`
  - 제목 `.view_head h3 span[id$=lbl_Title]`
  - 작성자 `span[id$=lbl_Writer]`(앞의 `<strong>작성자</strong>` 제거), 문의전화 `span[id$=lbl_Phone]`, 작성일 `span[id$=lbl_WriteDate]` (`2026.09.11 13:21`)
  - 첨부: `div[id$=pnl_Files] .view_info_file a[href*="bbsMode=download&fileCode="]` (미리보기 `a.preview_btn` 는 제외)
  - 본문: `.view_body .con` — **이미지만 있는 공지가 많다** (`img.ckeditorimg[src="./byteToImage.aspx?key=…"]`). 이 경우 `body_is_image_only=True`.
- 실측 특징: 교외 재단 공지는 제목이 `[장학안내][(재)○○장학재단] …` 꼴. 본문은 이미지+HWP 공고문인 비율이 절반 이상 → OCR(`DOC_PARSER`) 없이는 '확인 필요'.

## 2. 학과·단과대 홈페이지 — K2Web Wizard (`k2web`)

전남대 하위 사이트(학과·단과대·부속기관) 대부분이 같은 CMS 를 쓴다. URL 패턴 `/bbs/<site>/<boardNo>/…`.

| 사이트 | site | board | 말머리(bbsOpenWrdSeq) |
|---|---|---|---|
| 인공지능학부 aisw.jnu.ac.kr | `aisw` | `64` | 45 공지사항 · 236 학사 · **237 장학** · 238 행사 · 239 SW중심대학 · 240 인공지능혁신융합대학 · 536 정보보호특성화대학 |
| AI융합대학 cvg.jnu.ac.kr | `cvg` | `405` | 없음 (제목 키워드로 거름) |
| 소프트웨어공학과 sw.jnu.ac.kr | `sw` | `8265`(공지) | 미확인 |

- 목록: `GET /bbs/<site>/<board>/artclList.do?page=N&bbsOpenWrdSeq=<말머리>` (원래 폼은 POST 이지만 GET 쿼리도 동작)
  - `table.board-table tbody tr` → `td.td-subject a[href="/bbs/<site>/<board>/<글번호>/artclView.do"]`, `td.td-write`, `td.td-date`(`YYYY.MM.DD`), `td.td-file`
  - `tr.notice td.td-num span` = "일반공지"(고정 공지, 말머리 필터를 걸어도 섞여 옴)
  - 페이지네이션 `div._paging` (`javascript:page_link('N')`), 총 건수 `.util-search strong`
- 상세: `/bbs/<site>/<board>/<글번호>/artclView.do`
  - 제목 `.view-info h2.view-title` (`[장학]` 말머리 + 제목, 공백 정리 필요)
  - 메타 `dl > dt/dd` (작성일 · 수정일 · 작성자 · 조회수)
  - 본문 `.view-con`, 첨부 `.view-file a[href$="download.do"]`
- **RSS**: `/bbs/<site>/<board>/rssList.do?row=50` (title/link/pubDate/author/description) — 목록 파싱이 깨지면 대안.

## 3. 인공지능혁신융합대학사업단 AICOSS (`aicoss`)

- 목록: `https://aicoss.kr/www/notice/?page=N&searchOption=<분류>&searchItem=<검색어>&cate=`
  - 분류(select#ex_select): 글로벌 · 교과 · 비교과 · 행사 · 경진대회 · **학생지원** · 기자재 · AICOSS레터 · 기타
  - `table.basicBoard tbody tr` → `a[href="javascript:movePageView(<id>)"]`, 안에 `span.boardCat-wrap > span`(분류), `strong.cutText`(제목); `td.mobileNone`(날짜 `YYYY.MM.DD`, 조회)
  - `input#b_link_<id>` 값이 `"0"` 이면 내부 글, 아니면 외부 링크 글
  - 페이지네이션 `ul.pageBtn` (`movePage(N)`), 총 페이지 `span.totalPage`
- 상세: `https://aicoss.kr/www/notice/view/<id>` → `section.viewContainer h3`, `.viewContainer-info li`(`YYYY.MM.DD HH:MM`), `.viewContainer-content`(에디터 이미지 `/upload/editor/…` 위주)
- 상시 장학 안내: `/www/program/scholarship` (성과형·근로·성적우수 — 마일리지 제도 연동). 공지가 아니라 수집하지 않는다.

## 4. 학사정보시스템 내학사행정 hakstd.jnu.ac.kr (`hakstd`, SSO)

### 인증 (eclass_agent 와 동일 체계)
- SP 시작 → `idpm.jnu.ac.kr/IDP/dispatch?SAMLRequest=…` → 로그인 필요하면 `sso.jnu.ac.kr/Idp/Login.aspx` (폼 `#userId` `#userPwd` `#btnLoginButton`, 키보드보안 없음)
- `.jnu.ac.kr` 도메인 쿠키(`RathonSSO_SESSION`, `SSOValidate`, `WebSSOInfo` …)가 살아 있으면 e클래스·포털·학사시스템 어디든 비밀번호 없이 통과. 신뢰기기 쿠키 `RathonSSO_TrustDevice_*`(idpm, ~1년)가 2차 인증을 면제.
- SSO 서버 세션은 수 시간. 죽으면 `eclass_agent/login.py: reauthenticate()` 가 (쿠키 복구 →) DPAPI 자격증명으로 무인 로그인. **비밀번호는 eclass_agent 코드만 다룬다.**
- 도착 판정: 최종 URL 이 `hakstd.jnu.ac.kr/...` 이고 `sso.jnu.ac.kr`/`idpm.jnu.ac.kr` 가 아니면 로그인됨. 로그인 폼(`#userPwd`)이 보이면 실패.

### 장학 메뉴 지도 (`/web/Jang/…`)
| 메뉴 | 경로 | 용도 |
|---|---|---|
| 장학내역 조회 | `Jang010` | 본인 수혜 이력 (년도·학기·장학재단명·금액) |
| **학생 맞춤형 장학 안내** | `Jang011` | `table#…gvData` : 장학명 \| 지원조건(한 줄) \| 선발인원 \| 문의처 \| 바로가기(→ Jang012#장학명). 27행 |
| **전체 장학 안내** | `Jang012` | `div.content > h4(장학명) + div.img-box .cont ul.bullet(1. 지원대상 / 2. 성적기준 / 3. 지원금액 …)` 반복. 96항목(대학원·조교 포함) |
| 국가근로 장학신청 | `Jang040` | 신청 화면 (도구는 열지 않음) |
| 열정장학 확인서 업로드 | `Jang130` | |
| 미래성장 장학 신청 | `Jang101` (안내 `Jang110`) | |
| 도전장학신청(계획서 작성) | `Jang711` (안내 `Jang700`) | |
| 느티나무 장학 신청 | `Jang810` (안내 `Jang800`) | |
| 저소득(창조) 장학금 신청 | `Jang020` | |
| 응원장학 신청 | `Jang910` (안내 `Jang900`) | |
| 학생성공지원금 신청 | `Jang150` | |
| 기타장학 | `Jang200` | |

### 프로필 자동 채움에 쓰는 화면
- `/Home/DashBoard` → `div.infotext` : `이름 | 학번 | N 학년 | 재학 | 성별 | 주전공 : <단과대> / <학부>` (이름·학번은 읽지 않음) ; `#Score` : `성적(비교) | 3.xx | / 4.5`
- `/web/Sung/Sung010` 기이수성적 → `input[id$=ibtnSearch]` 클릭 후 `table#…gvData` (년도 · 학기 · 교과구분 · 교과목번호 · 교과목명 · 성적 · 학점 · 교과목상태 · 재이수 · 교양영역)
  - 학기 칸: 정규 `1`/`2`, 계절 `하계 계절`/`동계 계절`. **년도 칸이 `학기 평점` 인 합계 행이 섞여 있다 → 4자리 연도 아닌 행은 제외**
  - 취득학점 = 성적이 F/NP/U/W 가 아니고 상태에 포기·취소가 없는 행의 학점 합
- `/web/Hakj/Hakj010` 은 '기본정보변경'(연락처 폼)이라 학적 요약이 없다 — 대시보드를 쓴다.
- 페이지는 ASP.NET WebForms (`__VIEWSTATE`, `WebForm_DoPostBackWithOptions`) — 링크 대신 페이지 URL 직접 이동이 안전하다.

## 5. 국제협력과 international.jnu.ac.kr (`jnu_aspx` 변형)

- 목록: `https://international.jnu.ac.kr/Board/Board.aspx?BoardID=3&Mode=List&PageNum=N` → `table.board_list#…grvwList tr` (tbody 없음), `td.title a[href*="Mode=View"&"Seq=<글번호>"]` — **글 번호는 `Seq`**, 날짜 `YYYY-MM-DD`
- 상세: `Board.aspx?BoardID=3&Mode=View&Seq=<글번호>` → `.board_view_wrap .view_head p.title`, `span[id$=lbl_name]`, `span[id$=lbl_date]`, 첨부 `.view_info_file a[href*="ByteToFile.aspx?Seq=…&filename=…"]`, 본문 `.view_body .con`
- **TLS**: 서버가 중간 인증서를 보내지 않아 certifi 만으로는 `CERTIFICATE_VERIFY_FAILED`. `verify=False` 대신 `truststore` 로 OS 신뢰 저장소를 쓴다 (`scripts/http.py`).

## 6. 포털 portal.jnu.ac.kr (참고)

SSO 로그인 후 `/Pages/` 한 화면에 위젯으로 모아 보여준다. 각 위젯의 "더보기" 가 원본 게시판이다.
단과대학 공지 → cvg `/bbs/cvg/405/artclList.do` · 학부(과) 공지 → aisw `/bbs/aisw/64/artclList.do` · 학사안내 → www `boardID=5&cate=5` · 장학안내 → www `boardID=5&cate=8` · 취업·진로 → capd.jnu.ac.kr `Board.aspx?boardID=2` · 포털 공지 → `/Board/default2.aspx?bc=T0019` · 정보보안 → ucc.jnu.ac.kr · 내학사행정 → hakstd.jnu.ac.kr

## 아직 안 붙인 소스 (필요 시)
- 대학일자리플러스센터 capd.jnu.ac.kr (취업연계 장학·희망사다리) — `jnu_aspx` 계열로 추정
- 한국장학재단 kosaf.go.kr (국가장학금 일정) — 별도 사이트, 공지는 학교 게시판에 재게시되므로 우선순위 낮음
- e클래스 사이트 공용 공지(ubboard cmid<100) — 장학 글은 드묾
