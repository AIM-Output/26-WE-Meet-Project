"""테스트 공통 — 임시 data/ 를 쓴다. 내 브리핑(C4_Briefing_agent/data)도, 다른 기능의 DB 도 건드리지 않는다.

C4 는 재료를 넘겨받기만 하므로(service.Sources) 테스트는 가짜 재료 함수를 넘긴다. LLM 은 끈다(C4_LLM=off) —
한 줄 요약은 headline_chat 을 바꿔 끼워서만 시험한다.
"""
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="c4test_"))
os.environ["C4_DATA_DIR"] = str(_TMP / "c4data")
os.environ["C4_LLM"] = "off"
for k in ("LLM_MAIN_BASE_URL", "LLM_MAIN_API_KEY", "LLM_MAIN_MODEL"):
    os.environ[k] = ""
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

NOW = datetime(2026, 10, 26, 8, 0)          # 월요일 08:00 — 기본 브리핑 시각


@pytest.fixture(autouse=True)
def clean_db():
    from briefing import config as C
    if C.DB_PATH.exists():
        C.DB_PATH.unlink()
    yield
    if C.DB_PATH.exists():
        C.DB_PATH.unlink()


def ev(eid, title, start, kind="user", end=None, all_day=False, **props):
    """/api/events 의 CalEvent 모양 (C1 5절)."""
    return {"id": eid, "title": title, "start": start, "end": end, "allDay": all_day, "editable": kind == "user",
            "extendedProps": {"kind": kind, **props}}


def deadline(eid, title, due, course="운영체제", etype="과제", done=False):
    return ev(eid, title, due, kind="deadline", due=due, courseShort=course, type=etype, done=done, removed=False)


def ingredients():
    """하루치 재료 — 요구사항정의서 F10 5절 템플릿 예시를 이 앱의 실제 모양으로 옮긴 것 (2026-10-26 월)."""
    return {
        "classes": {
            "date": "2026-10-26",
            "classes": [
                {"id": "cl:os:2026-10-26", "courseId": "c-os", "name": "운영체제", "start": "13:00", "end": "13:50",
                 "room": "공7-223", "state": "scheduled", "level": "safe", "levelLabel": "안전"},
                {"id": "cl:net:2026-10-26", "courseId": "c-net", "name": "컴퓨터네트워크", "start": "09:00", "end": "09:50",
                 "room": "공6-105", "state": "scheduled", "level": "danger", "levelLabel": "위험"},
                {"id": "cl:se:2026-10-26", "courseId": "c-se", "name": "소프트웨어공학론", "start": "15:00", "end": "15:50",
                 "room": "", "state": "canceled", "level": "safe", "levelLabel": "안전"},
            ],
            "totals": {"risky": [{"id": "c-net", "name": "컴퓨터네트워크", "level": "danger", "levelLabel": "위험",
                                  "remaining": 0.5, "spareSessions": 0}]},
        },
        "events": [
            ev("12", "스터디 모임", "2026-10-26T19:00:00", end="2026-10-26T21:00:00", isTodo=False, done=False),
            ev("13", "보고서 양식 출력", "2026-10-26", all_day=True, end="2026-10-27", isTodo=True, done=False),
            ev("14", "끝낸 할 일", "2026-10-26", all_day=True, end="2026-10-27", isTodo=True, done=True),
            ev("15", "어제 일정", "2026-10-25T10:00:00"),
            ev("ac:mid", "중간고사 기간", "2026-10-26", kind="academic", all_day=True, end="2026-10-31", refId="ac:mid"),
            ev("ex:os-mid", "운영체제 중간고사", "2026-10-26T10:30:00", kind="exam", examId="ex:os-mid",
               place="공7-101", timeUnknown=False, href="/exams?exam=ex:os-mid"),
            ev("cl:os:2026-10-26", "운영체제", "2026-10-26T13:00:00", kind="class"),
            deadline("dl:1", "퀴즈 2회", "2026-10-26T23:59:00", course="컴퓨터네트워크", etype="퀴즈"),
            deadline("dl:2", "3주차 실습", "2026-10-28T00:00:00"),                    # 자정 마감 = 10/27(내일) 24:00
            deadline("dl:3", "품질 보고서", "2026-10-29T18:00:00", course="소프트웨어공학론"),
            deadline("dl:4", "다음 주 과제", "2026-11-02T23:59:00"),                   # D-7 — 빠진다
            deadline("dl:5", "제출한 과제", "2026-10-27T23:59:00", done=True),         # 제출 완료 — 빠진다
            deadline("dl:6", "지난 과제", "2026-10-25T23:59:00"),                      # 지난 마감 — '주의' 의 놓친 마감 몫
        ],
        "priority": {
            "items": [
                {"id": "dl:1", "title": "퀴즈 2회", "courseShort": "컴퓨터네트워크", "reason": "마감 15시간 전 · 30분 필요"},
                {"id": "dl:2", "title": "3주차 실습", "courseShort": "운영체제", "reason": "마감 1일 전 · 2시간 필요"},
                {"id": "dl:3", "title": "품질 보고서", "courseShort": "소프트웨어공학론", "reason": "마감 3일 전 · 5시간 필요"},
            ],
            "totalText": "7시간 30분", "overdue": 1,
        },
        "academic": [
            {"id": "ac:reg", "title": "수강 철회", "start": "2026-10-28", "daysLeft": 2,
             "reminders": [{"code": "d3", "enabled": True}]},
            {"id": "ac:off", "title": "수업일수 1/2", "start": "2026-10-27", "daysLeft": 1, "reminders": []},
            {"id": "ac:leave", "title": "일반휴학 (등록)", "start": "2026-08-18", "daysLeft": -69, "endsIn": 2,   # 긴 기간의 끝
             "reminders": [{"code": "end1", "enabled": True}]},
            {"id": "ac:long", "title": "학기 중 상시 신청", "start": "2026-09-01", "daysLeft": -55, "endsIn": 40,
             "reminders": [{"code": "d3", "enabled": True}]},
            {"id": "ac:mid", "title": "중간고사 기간", "start": "2026-10-26", "daysLeft": 0,
             "reminders": [{"code": "d3", "enabled": True}]},
        ],
        "study": {
            "blocks": [{"examId": "ex:net-mid", "course": "컴퓨터네트워크", "text": "컴퓨터네트워크 22쪽 (40분)", "done": False}],
            "nextExam": {"examId": "ex:net-mid", "course": "컴퓨터네트워크", "typeLabel": "중간고사", "dday": 2,
                         "time": "10:30", "place": ""},
        },
        "blocks": {"blocks": [
            {"id": "pb:7", "title": "품질 보고서", "start": "11:00", "end": "12:00", "done": False, "href": "",
             "taskType": "assignment"},
            {"id": "pb:8", "title": "끝낸 블록", "start": "16:00", "end": "17:00", "done": True, "href": "", "taskType": "todo"},
        ]},
        "scholarships": [{"id": "sch1", "title": "지역인재 장학금", "daysLeft": 1, "progress": "초안 대기"}],
        "activities": [{"id": "act1", "title": "SW 공모전", "daysLeft": 3, "progress": "담음"}],
        "alerts": [
            {"id": "att:c-net:x", "kind": "attendance", "refId": "c-net", "title": "컴퓨터네트워크 결석 위험",
             "body": "한 번 더 결석하면 F", "href": "/attendance?course=c-net", "deliveredAt": "2026-10-25T20:00:00", "read": False},
            {"id": "sch-new:1", "kind": "scholarship", "refId": "sch1", "title": "새 장학 1건", "body": "",
             "href": "/scholarships?item=sch1", "deliveredAt": "2026-10-26T06:10:00", "read": False},
            {"id": "rem:ac:reg:d3:202610250900", "kind": "academic", "refId": "ac:reg", "title": "D-3 · 수강 철회",
             "deliveredAt": "2026-10-25T09:00:00", "read": False},
            {"id": "dl:1:d1:202610250900", "kind": "deadline", "refId": "dl:1", "title": "내일 마감 · 퀴즈 2회",
             "deliveredAt": "2026-10-25T09:00:00", "read": False},
            {"id": "dl-new:20261026", "kind": "deadline", "refId": None, "title": "새 과제 2건", "body": "운영체제 · 품질 보고서",
             "href": "/assignments?tab=open", "deliveredAt": "2026-10-26T04:05:00", "read": False},
            {"id": "briefing:2026-10-25", "kind": "briefing", "title": "오늘 브리핑이 도착했습니다",
             "deliveredAt": "2026-10-25T08:00:00", "read": False},
            {"id": "old", "kind": "eclass", "title": "오래된 공지", "deliveredAt": "2026-10-20T08:00:00", "read": False},
        ],
    }


class FakeSources:
    """service.Sources 를 가짜 재료로 — 부른 횟수·알림을 기록한다."""

    def __init__(self, ing=None, busy=None, fail=()):
        from briefing.service import Sources
        self.ing = ingredients() if ing is None else ing
        self.busy_names = list(busy or [])
        self.notified = []
        self.calls = 0

        def loader(key):
            def fn(*args):
                self.calls += 1
                if key in fail:
                    raise RuntimeError(f"{key} 고장")
                return self.ing.get(key)
            return fn

        self.src = Sources(**{k: loader(k) for k in ("classes", "events", "priority", "academic", "study", "blocks",
                                                      "scholarships", "activities", "alerts")},
                           busy=lambda: list(self.busy_names),
                           notify=lambda *a: self.notified.append(a))
