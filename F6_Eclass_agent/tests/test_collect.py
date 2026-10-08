"""수집기 해석 규칙 — 날짜 · 캘린더 · 퀴즈 마감 · 병합 · 네트워크 오류 판정 (e클래스에 접속하지 않는다)."""
from datetime import date

from bs4 import BeautifulSoup

from eclass import collect

TODAY = date(2026, 9, 28)


def test_parse_kdate_variants():
    assert collect.parse_kdate("2026년 9월 15일(화요일), 23:59", TODAY) == "2026-09-15 23:59"
    assert collect.parse_kdate("2026년 9월 15일 오후 11:59", TODAY) == "2026-09-15 23:59"
    assert collect.parse_kdate("2026년 9월 15일 오전 12:30", TODAY) == "2026-09-15 00:30"
    assert collect.parse_kdate("내일, 09:00", TODAY) == "2026-09-29 09:00"
    assert collect.parse_kdate("2026-09-16 16:00", TODAY) == "2026-09-16 16:00"
    assert collect.parse_kdate("2026-10-5 00:00", TODAY) == "2026-10-05 00:00"      # 과제 화면 실측 (0 을 안 붙인다)
    assert collect.parse_kdate("알 수 없음", TODAY) == "알 수 없음"


CAL = """
<div class="event"><h3 class="referer"><a href="https://sel.jnu.ac.kr/mod/vod/view.php?id=1500001">4주차 강의</a></h3>
  <img class="icon" title="동영상" src="x.png"><div class="course"><a href="#">컴퓨터그래픽스[2] (CIS3020)</a></div>
  <div class="date">2026년 9월 21일(월요일), 00:00 » 2026년 10월 4일(일요일), 23:59</div></div>
<div class="event"><h3 class="referer"><a href="https://sel.jnu.ac.kr/mod/quiz/view.php?id=1500002">퀴즈 2회</a></h3>
  <img class="icon" title="퀴즈" src="x.png"><div class="course"><a href="#">컴퓨터네트워크[1] (ECE3026)</a></div>
  <div class="date">내일, 23:59</div></div>
"""


def test_parse_calendar():
    ev = collect.parse_calendar(BeautifulSoup(CAL, "html.parser"), TODAY)
    assert [(e["cmid"], e["mod"], e["type"]) for e in ev] == [("1500001", "vod", "동영상"), ("1500002", "quiz", "퀴즈")]
    assert (ev[0]["start"], ev[0]["end"]) == ("2026-09-21 00:00", "2026-10-04 23:59")
    assert (ev[1]["start"], ev[1]["end"]) == ("", "2026-09-29 23:59")


def test_quiz_close_reads_only_close_time():
    html = """<div class="quizinfo"><p>응시 가능 횟수: 1</p><p>시작 일시: 2026년 9월 25일(금요일), 09:00</p>
              <p>이 퀴즈는 2026년 10월 2일(금요일), 23:59에 종료됩니다.</p><p>제한 시간: 30 분</p></div>"""
    assert collect.quiz_close(BeautifulSoup(html, "html.parser"), TODAY) == "2026-10-02 23:59"
    html2 = '<div class="quizinfo"><p>종료 일시: 2026-10-05 18:00</p></div>'
    assert collect.quiz_close(BeautifulSoup(html2, "html.parser"), TODAY) == "2026-10-05 18:00"
    assert collect.quiz_close(BeautifulSoup('<div class="quizinfo"><p>시간 제한 없음</p></div>', "html.parser"), TODAY) == ""


def test_assignment_status_table():
    html = """<table class="generaltable"><tr><th>제출 여부</th><td>제출 완료</td></tr>
              <tr><th>종료 일시</th><td>2026년 9월 16일(수요일), 16:00</td></tr><tr><th>x</th><td>___y___</td></tr></table>"""
    st = collect.parse_assignment_status(BeautifulSoup(html, "html.parser"))
    assert st == {"제출 여부": "제출 완료", "종료 일시": "2026년 9월 16일(수요일), 16:00"}


def test_merge_deadlines_prefers_assignment_page():
    a = {"url": "https://sel.jnu.ac.kr/mod/assign/view.php?id=7", "due": "2026-10-03 23:59", "course": "과목", "course_id": "1",
         "name": "과제", "cmid": "7", "submitted": "제출 완료"}
    ev = {"url": a["url"], "end": "2026-10-01 23:59", "start": "", "course": "과목", "type": "과제", "name": "과제", "cmid": "7"}
    q = {"url": "https://sel.jnu.ac.kr/mod/quiz/view.php?id=8", "due": "2026-10-02 23:59", "course": "과목", "course_id": "1",
         "name": "퀴즈", "cmid": "8"}
    items = collect.merge_deadlines([ev], [a], [q, {**q, "cmid": "9", "url": "u9", "due": ""}], [{"name": "과목", "id": "1"}])
    assert [(i["cmid"], i["due"], i["source"], i["status"]) for i in items] == [
        ("8", "2026-10-02 23:59", "quiz", ""), ("7", "2026-10-03 23:59", "calendar", "제출 완료")]


def test_calendar_short_course_name_resolves():
    """캘린더는 과목을 '소프트웨어공학론' 처럼 줄여 적는다 (2026-09-30 실측) → 정식 이름·id 로."""
    courses = [{"id": "74261", "name": "소프트웨어공학론[1] (CIS3030)"}, {"id": "74245", "name": "운영체제[2] (CIS2001)"}]
    assert collect.resolve_course("소프트웨어공학론", courses)["id"] == "74261"
    assert collect.resolve_course("운영체제[2] (CIS2001)", courses)["id"] == "74245"
    assert collect.resolve_course("없는 과목", courses) is None
    ev = {"url": "https://sel.jnu.ac.kr/mod/vod/view.php?id=9", "end": "2026-10-01 23:59", "start": "", "course": "운영체제",
          "type": "동영상", "name": "강의", "cmid": "9"}
    (item,) = collect.merge_deadlines([ev], [], [], courses)
    assert (item["course"], item["course_id"]) == ("운영체제[2] (CIS2001)", "74245")


def test_network_error_detection():
    assert collect.is_network_error(Exception("Error: getaddrinfo ENOTFOUND sel.jnu.ac.kr"))
    assert collect.is_network_error(Exception("net::ERR_INTERNET_DISCONNECTED"))
    assert collect.is_network_error(collect.NetworkError("x"))
    assert not collect.is_network_error(ValueError("형식 오류"))
    assert collect.cmid_of("https://sel.jnu.ac.kr/mod/assign/view.php?id=1461455") == "1461455"


# ---------------------------------------------------------------- 동영상 (2026-10-02 실측 모양을 줄인 것 — 개인정보 없음)

COURSE_VOD = """
<li class="activity vod modtype_vod" id="module-1445823"><div class="activityinstance">
  <a href="https://sel.jnu.ac.kr/mod/vod/view.php?id=1445823" onclick="window.open('...viewer.php?id=1445823')">
  <img alt="동영상" class="activityicon" src="x"/><span class="instancename">수업 동영상 (Orientation - 9월 15일까지)</span></a>
  <span class="displayoptions"><span class="text-ubstrap"> 2026-09-01 00:00:00 ~ 2026-09-15 23:59:00</span><span class="text-info">, 13:40</span></span>
</div></li>
<li class="activity vod modtype_vod" id="module-1445825"><div class="activityinstance">
  <a href="https://sel.jnu.ac.kr/mod/vod/view.php?id=1445825"><span class="instancename">동영상 강의 (9월 8일 수업_9월 14일까지) </span></a>
  <span class="displayoptions"><span class="text-ubstrap"> 2026-09-01 00:00:00 ~ 2026-09-14 23:59:00 (지각 : 2026-09-21 23:59:00)</span><span class="text-info">, 56:13</span></span>
</div></li>
"""

PROGRESS = """
<table class="table table-bordered"><tr><th>학번</th><td>(읽지 않는다)</td></tr></table>
<table class="table table-bordered user_progress">
<tr><th>주</th><th>강의 자료</th><th>콘텐츠 길이</th><th>출석인정 요구시간</th><th>최대 학습위치</th><th>진도율</th></tr>
<tr><td class="vmiddle text-center"><div class="sectiontitle">1</div></td><td class="text-left"><img src="x"/> 수업 동영상 (Orientation - 9월 15일까지)</td>
<td class="text-center">13:40</td><td class="text-center">12:17</td><td class="text-center">13:40<br/><button>상세보기 (3)</button></td><td class="text-center">100%</td></tr>
<tr><td class="vmiddle text-center" rowspan="2"><div class="sectiontitle">2</div></td><td class="text-left"><img src="x"/> 동영상 강의 (9월 8일 수업_9월 14일까지) </td>
<td class="text-center">56:13</td><td class="text-center">50:35</td><td class="text-center">20:00<br/><button>상세보기 (1)</button></td><td class="text-center">36%</td>
<tr><td class="text-left"><img src="x"/> 9월 10일 동영상 수업 (9월 14일까지)</td><td class="text-center">47:29</td><td class="text-center">42:44</td>
<td class="text-center">47:29</td><td class="text-center">90%</td></tr></tr>
</table>
"""


def test_vod_period_takes_attendance_deadline_only():
    soup = BeautifulSoup(COURSE_VOD, "html.parser")
    acts = {}
    for li in soup.select("li.modtype_vod"):
        acts[li["id"]] = collect.vod_period(collect.text_of(li.select_one(".displayoptions")))
    assert acts["module-1445823"] == {"vodStart": "2026-09-01 00:00", "vodEnd": "2026-09-15 23:59", "length": "13:40"}
    assert acts["module-1445825"]["vodEnd"] == "2026-09-14 23:59"          # 지각 기간은 마감으로 쓰지 않는다
    assert acts["module-1445825"]["length"] == "56:13"


def test_vod_progress_watched_rule():
    rows = collect.parse_vod_progress(BeautifulSoup(PROGRESS, "html.parser"))
    p = {r["name"]: r for r in rows}
    assert list(p) == ["수업 동영상 (Orientation - 9월 15일까지)", "동영상 강의 (9월 8일 수업_9월 14일까지)", "9월 10일 동영상 수업 (9월 14일까지)"]
    assert p["수업 동영상 (Orientation - 9월 15일까지)"]["watched"] is True
    assert p["동영상 강의 (9월 8일 수업_9월 14일까지)"] == {"name": "동영상 강의 (9월 8일 수업_9월 14일까지)", "length": "56:13",
                                                     "required": "50:35", "progress": 36.0, "watched": False}
    assert p["9월 10일 동영상 수업 (9월 14일까지)"]["watched"] is True     # 요구시간 42:44/47:29 = 89.99% → 90% 면 인정


def _progress_table(rows: list[tuple[str, str, str, str]], heads=("주", "강의 자료", "콘텐츠 길이", "출석인정 요구시간",
                                                                  "최대 학습위치", "진도율")) -> BeautifulSoup:
    trs = "".join(f'<tr><td class="vmiddle text-center">{i + 1}</td><td class="text-left">{n}</td><td>{ln}</td><td>{rq}</td>'
                  f'<td>{ln}</td><td>{pg}</td></tr>' for i, (n, ln, rq, pg) in enumerate(rows))
    th = "".join(f"<th>{h}</th>" for h in heads)
    return BeautifulSoup(f'<table class="user_progress"><tr>{th}</tr>{trs}</table>', "html.parser")


def test_vod_progress_same_name_each_week_matches_in_order():
    """주차마다 '강의 동영상' 처럼 같은 이름 — 예전엔 첫 주 진도율을 모든 주에 썼다 (본 동영상이 미시청으로 보임)."""
    rows = collect.parse_vod_progress(_progress_table([("강의 동영상", "10:00", "09:00", "20%"),
                                                       ("강의 동영상", "10:00", "09:00", "100%")]))
    vods = [{"cmid": "11", "name": "강의 동영상"}, {"cmid": "12", "name": "강의 동영상"}]
    m = collect.match_vod_progress(vods, rows)
    assert (m["11"]["watched"], m["12"]["watched"]) == (False, True)


def test_vod_progress_shortened_or_respaced_name():
    rows = collect.parse_vod_progress(_progress_table([("3주차 운영체제 프로세스 스케줄링 (1)...", "30:00", "27:00", "100%"),
                                                       ("4주차  동기화", "30:00", "27:00", "95%")]))
    vods = [{"cmid": "1", "name": "3주차 운영체제 프로세스 스케줄링 (1) 다중 큐와 우선순위"}, {"cmid": "2", "name": "4주차 동기화"}]
    m = collect.match_vod_progress(vods, rows)
    assert m["1"]["watched"] and m["2"]["watched"]


def test_vod_progress_columns_by_header_and_attendance_mark():
    """칸 순서가 달라도 머리글로 찾고, 출석(O/X) 칸이 있으면 그것을 믿는다."""
    soup = BeautifulSoup('<table class="user_progress"><tr><th>강의 자료</th><th>출석인정 요구시간</th><th>콘텐츠 길이</th>'
                         '<th>진도율</th><th>출석</th></tr>'
                         '<tr><td class="text-left">1강</td><td>45:00</td><td>50:00</td><td>89%</td><td>O</td></tr>'
                         '<tr><td class="text-left">2강</td><td>45:00</td><td>50:00</td><td>40%</td><td>X</td></tr></table>',
                         "html.parser")
    rows = collect.parse_vod_progress(soup)
    assert [(r["length"], r["required"], r["progress"], r["watched"]) for r in rows] == [
        ("50:00", "45:00", 89.0, True), ("50:00", "45:00", 40.0, False)]


def test_videos_replace_calendar_period():
    v = {"course_id": "74259", "course": "컴퓨터그래픽스[2] (CIS3020)", "cmid": "1500001", "name": "4주차 강의",
         "url": "https://sel.jnu.ac.kr/mod/vod/view.php?id=1500001", "due": "2026-10-04 23:59", "status": "미시청",
         "description": "콘텐츠 길이 50:00"}
    ev = {"url": v["url"], "start": "2026-09-21 00:00", "end": "2026-10-11 23:59", "course": "컴퓨터그래픽스", "type": "동영상",
          "name": v["name"], "cmid": "1500001"}
    (item,) = collect.merge_deadlines([ev], [], [], [{"id": "74259", "name": v["course"]}], [v])
    assert (item["start"], item["due"], item["source"], item["status"]) == ("", "2026-10-04 23:59", "vod", "미시청")


def test_uploaded_at_from_last_modified():
    """파일 응답의 Last-Modified = e클래스에 올린 시각 (2026-10-03 실측: week 5.ppt 'Thu, 01 Oct 2026 04:15:48 GMT')."""
    got = collect.uploaded_at({"Last-Modified": "Thu, 01 Oct 2026 04:15:48 GMT"})
    assert got is not None and got.startswith("2026-10-01T")
    from datetime import datetime, timezone
    assert got == datetime(2026, 10, 1, 4, 15, 48, tzinfo=timezone.utc).astimezone().replace(tzinfo=None).isoformat(timespec="seconds")
    assert collect.uploaded_at({}) is None and collect.uploaded_at({"last-modified": "nonsense"}) is None
