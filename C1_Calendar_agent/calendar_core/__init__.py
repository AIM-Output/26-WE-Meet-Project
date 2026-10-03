"""C1 서비스 캘린더 — 공통 기반 (Univ-Us). 구조는 ../README.md.

전부 표준 라이브러리 + fastapi — config · store · service · api
모든 기능(F1·F3·F5·F6·F8·F9·F11·F16)이 일정을 여기로 모은다. 캘린더가 제품의 본체다 (전역 결정 G1).

패키지 이름이 `calendar` 가 아닌 이유: 대시보드 백엔드가 이 폴더를 sys.path 에 넣기 때문에
`calendar/` 로 두면 파이썬 표준 라이브러리의 calendar 모듈을 가려 버린다(http.cookiejar 등이 쓴다).
"""
