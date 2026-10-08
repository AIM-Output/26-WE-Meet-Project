"""배치 규칙 — F8 5절 ②·③ · F8-R11~R17 + 남는 공강의 공부 블록 (2026-10-07)."""
import time
from datetime import date, timedelta

from conftest import FRI, NOW, THU, TUE, WED, cls, exam, spec, task, todo, tuesday_classes
from placement import rules, service, slots


def run(events, items, exams=(), settings=None, now=NOW, days=7):
    settings = settings or spec()
    ds = slots.day_range(now.date(), days)
    first, last = ds[0].isoformat(), ds[-1].isoformat()
    classes, busy = service.split_events(events)
    free = slots.build(ds, classes, busy, settings, now)
    tasks = rules.order(service.todo_tasks(events, [], now, settings, first, last),
                        service.assignment_tasks(items, [], now))
    res = rules.place(tasks, free, settings, now, last)
    res["study"] = rules.fill_study(res["free"], service.study_targets(exams), settings) if settings["fillStudy"] else []
    return res


def spans(blocks, ref=None):
    return [(b["date"], b["start"], b["end"]) for b in blocks if ref is None or b["refId"] == ref]


def test_example_tuesday():
    """화요일 공강 11:00~12:00 · 15:00~18:00 — 할 일 → 과제 → 남는 공강은 공부."""
    res = run(tuesday_classes() + [todo(7, TUE, "장학금 서류")],
              [task("dl:4", "품질 보고서", f"{FRI}T18:00:00", 5, slack=60)],
              [exam("ex:os", "운영체제", "2026-10-20", percent=0), exam("ex:se", "소프트웨어공학론", THU, percent=50)],
              days=1)
    assert spans(res["blocks"], "todo:7") == [(TUE, "11:00", "11:30")]
    assert spans(res["blocks"], "dl:4") == [(TUE, "11:30", "12:00"), (TUE, "15:00", "17:00")]   # 하루 2블록
    assert spans(res["study"]) == [(TUE, "17:00", "18:00")]
    s = res["study"][0]
    assert s["refId"] == "ex:se" and s["title"] == "소프트웨어공학론 중간고사 공부" and s["taskType"] == "study"
    assert s["reason"] == "남은 진도 50% · 시험 D-2 · 공강 180분"   # 0.5 ÷ 2일 > 1.0 ÷ 21일
    assert res["blocks"][0]["reason"] == "9/29 할 일 · 공강 60분"
    assert res["deferred"][0]["remainingMinutes"] == 150                      # 마감이 기간 뒤 — 실패가 아니다


def test_no_study_when_tasks_fill_everything():
    """과제가 공강을 다 쓰면 공부 블록은 없다 — 남는 공강만 채운다."""
    res = run([], [task("dl:1", "프로젝트", f"{TUE}T18:00:00", 8, slack=-1, group="now")],
              [exam("ex:a", "운영체제", THU)], spec(maxBlockMinutes=240, lunchBreak=False, dayEnd="17:00"), days=1)
    assert sum(b["minutes"] for b in res["blocks"]) == 480 and res["study"] == []


def test_no_daily_cap():
    """하루 상한 없음 (2026-10-06) — 자리가 있으면 하루에 4시간 넘게 들어간다."""
    items = [task(f"dl:{i}", f"과제{i}", f"{TUE}T18:00:00", 2, slack=i) for i in range(5)]
    res = run([], items, settings=spec(lunchBreak=False), days=1)
    assert sum(b["minutes"] for b in res["blocks"]) == 540 and len(res["unplaced"]) == 1


def test_assignment_never_after_due():
    """R11 — 마감 뒤에 배치하지 않는다. 마감 날은 마감 시각에서 자른다."""
    res = run([], [task("dl:1", "실습", f"{TUE}T11:00:00", 5, slack=-1, group="now")], days=1)
    assert spans(res["blocks"]) == [(TUE, "09:00", "11:00")]
    assert res["unplaced"][0]["remainingMinutes"] == 180 and res["unplaced"][0]["reasonKey"] == "noSlot"


def test_assignment_takes_earliest_slots():
    res = run(tuesday_classes(), [task("dl:1", "보고서", f"{THU}T23:59:00", 1, slack=10)])
    assert spans(res["blocks"]) == [(TUE, "11:00", "12:00")]


def test_order_follows_f7_priority():
    """R12 — F7 순서 그대로 (여유가 적은 것이 좋은 자리를 먼저)."""
    a = task("dl:a", "급함", f"{THU}T23:59:00", 2, slack=5)
    b = task("dl:b", "느긋", f"{THU}T23:59:00", 2, slack=40)
    res = run([], [a, b], days=1)
    assert spans(res["blocks"], "dl:a") == [(TUE, "09:00", "11:00")]
    assert spans(res["blocks"], "dl:b")[0] == (TUE, "11:00", "12:00")


def test_f7_order_is_not_resorted():
    """F7-R34 — slack 값이 뒤집혀 있어도 F7 이 준 순서를 지킨다."""
    a = task("dl:a", "첫째", f"{THU}T23:59:00", 2, slack=50)
    b = task("dl:b", "둘째", f"{THU}T23:59:00", 2, slack=5)
    out = rules.order([], service.assignment_tasks([a, b], [], NOW))
    assert [t["key"] for t in out] == ["dl:a", "dl:b"]


def test_todo_inserted_by_slack_and_late_todo_goes_first_free_slot():
    items = [task("dl:a", "A", f"{THU}T23:59:00", 2, slack=5), task("dl:b", "B", f"{FRI}T23:59:00", 2, slack=200)]
    evs = [todo(1, TUE), todo(2, "2026-09-25", "밀린 것"), todo(3, TUE, "끝낸 것", done=True)]
    s = spec()
    tasks = rules.order(service.todo_tasks(evs, [], NOW, s, TUE, "2026-10-05"), service.assignment_tasks(items, [], NOW))
    assert [t["key"] for t in tasks] == ["dl:a", "todo:1", "todo:2", "dl:b"]     # 여유 5h · 9.5h · 153.5h · 200h
    late = next(t for t in tasks if t["key"] == "todo:2")
    assert late["late"] and late["due"].date().isoformat() == "2026-10-05"
    res = run(evs, [], days=7)
    assert spans(res["blocks"], "todo:2") == [(TUE, "09:30", "10:00")]
    assert "(밀린 할 일)" in next(b for b in res["blocks"] if b["refId"] == "todo:2")["reason"]


def test_split_into_blocks_three_hours():
    """R13 — 3시간 과제가 2시간 + 1시간으로 (한 공강 안에서 이어서)."""
    res = run([], [task("dl:1", "보고서", f"{THU}T23:59:00", 3)], settings=spec(lunchBreak=False), days=1)
    assert [b["minutes"] for b in res["blocks"]] == [120, 60]
    assert [b["part"] for b in res["blocks"]] == ["1/2", "2/2"]


def test_max_block_two_hours():
    """R14 — 2시간 넘는 블록은 없다."""
    res = run([], [task("dl:1", "프로젝트", "2026-10-05T23:59:00", 12)])
    assert max(b["minutes"] for b in res["blocks"]) == 120


def test_same_task_two_blocks_per_day():
    """R16 — 같은 작업은 하루 최대 2블록."""
    res = run([], [task("dl:1", "프로젝트", f"{TUE}T23:59:00", 5)], settings=spec(lunchBreak=False), days=1)
    assert len(res["blocks"]) == 2 and res["unplaced"][0]["reasonKey"] == "sameTask"


def test_no_crumb_left_over():
    """30분 단위 — 남는 시간이 최소 길이보다 짧게 남지 않게 앞 블록을 줄인다 (130분 → 100 + 30)."""
    res = run([], [task("dl:1", "보고서", f"{THU}T23:59:00", 130 / 60)], settings=spec(lunchBreak=False), days=1)
    assert [b["minutes"] for b in res["blocks"]] == [100, 30]


def test_short_task_keeps_its_length():
    """원래 30분보다 짧은 작업(퀴즈 20분)은 그 길이로 들어간다."""
    res = run([], [task("dl:1", "퀴즈", f"{THU}T23:59:00", 20 / 60)])
    assert [b["minutes"] for b in res["blocks"]] == [20]


def test_reason_overdue():
    res = run([], [task("dl:1", "지난 과제", "2026-09-28T23:59:00", 2, group="overdue")])
    assert res["unplaced"][0]["reasonKey"] == "overdue"
    assert res["unplaced"][0]["reason"] == "이미 마감이 지났습니다"


def test_stale_overdue_and_nodue_are_not_targets():
    items = [task("dl:1", "오래된", "2026-09-01T23:59:00", 2, group="overdue", stale=True),
             task("dl:2", "마감 없음", None, 2, group="nodue")]
    assert service.assignment_tasks(items, [], NOW) == []


def test_reason_short():
    """30분 이상 연속 공강이 없다 — 앞 과제가 쓰고 20분 조각만 남은 날."""
    s = spec(dayStart="09:00", dayEnd="12:00")
    res = run([], [task("dl:a", "A", f"{TUE}T18:00:00", 160 / 60, slack=1), task("dl:b", "B", f"{TUE}T18:00:00", 1, slack=2)],
              settings=s, days=1)
    assert spans(res["blocks"], "dl:a") == [(TUE, "09:00", "11:00"), (TUE, "11:00", "11:40")]
    u = res["unplaced"][0]
    assert (u["refId"], u["reasonKey"], u["reason"]) == ("dl:b", "short", "30분 이상 연속 공강이 없습니다")


# ---------------------------------------------------------------- 공부 블록 (2026-10-07)

def test_study_score_rule():
    """점수 = 남은 진도율 ÷ 남은 날수 × 0.5^(그 날 같은 과목 수)."""
    d = date.fromisoformat(TUE)
    a = {"date": "2026-10-09", "percent": 40}            # 0.6 ÷ 10일
    assert abs(rules.study_score(a, d, 0) - 0.06) < 1e-9
    assert abs(rules.study_score(a, d, 1) - 0.03) < 1e-9
    assert rules.study_score({"date": TUE, "percent": 0}, d, 0) == 2.0   # 시험 당일 = 0.5일


def test_study_fills_free_day_alternating_subjects():
    """공강 날 — 점수가 높은 과목부터, 같은 날 같은 과목은 감점되어 번갈아, 하루 2블록까지."""
    exams = [exam("ex:a", "운영체제", THU, percent=0), exam("ex:b", "자료구조", "2026-10-09", percent=0)]
    res = run([], [], exams, spec(lunchBreak=False), days=1)
    got = [(b["start"], b["end"], b["refId"]) for b in res["study"]]
    # a: 1/2=0.5 → b: 1/10=0.1 vs a 0.25 → a … a 두 번이면 b
    assert got == [("09:00", "11:00", "ex:a"), ("11:00", "13:00", "ex:a"), ("13:00", "15:00", "ex:b"),
                   ("15:00", "17:00", "ex:b")]                      # 17~18시는 두 과목 다 2블록 — 비워 둔다


def test_progress_changes_the_choice():
    """진도를 많이 나간 과목은 시험이 가까워도 뒤로 — 남은 진도율이 기준."""
    exams = [exam("ex:a", "운영체제", WED, percent=95), exam("ex:b", "자료구조", "2026-10-03", percent=10)]
    res = run([], [], exams, spec(lunchBreak=False, dayEnd="11:00"), days=1)
    assert res["study"][0]["refId"] == "ex:b"            # 0.9÷4 = 0.225 > 0.05÷1


def test_done_or_past_exams_are_skipped():
    exams = [exam("ex:done", "A", THU, percent=100), exam("ex:past", "B", "2026-09-28")]
    assert run([], [], exams, days=1)["study"] == []


def test_exam_day_only_before_the_exam():
    """시험 당일은 시험 시작 전(여유 10분)까지만, 시각 미정 시험은 당일에 넣지 않는다."""
    res = run([], [], [exam("ex:a", "운영체제", TUE, time="11:00")], spec(lunchBreak=False), days=1)
    assert spans(res["study"]) == [(TUE, "09:00", "10:50")]
    assert "11:00 시험 전" in res["study"][0]["reason"]
    assert run([], [], [exam("ex:b", "자료구조", TUE)], days=1)["study"] == []


def test_fill_study_off():
    res = run([], [], [exam("ex:a", "운영체제", THU)], spec(fillStudy=False), days=1)
    assert res["study"] == []


def test_deterministic():
    """9절 — 같은 입력이면 같은 배치."""
    args = (tuesday_classes() + [todo(1, WED)],
            [task("dl:1", "A", f"{THU}T23:59:00", 3, slack=10), task("dl:2", "B", f"{THU}T23:59:00", 1, slack=10)],
            [exam("ex:a", "운영체제", FRI, 30), exam("ex:b", "자료구조", "2026-10-09", 0)])
    assert run(*args) == run(*args)


def test_adjustments_without_cap():
    """미배치가 있으면 조정 제안 — 낮 시간 늘리기 · 주말 · 점심. 상한 올리기 · 저녁은 없다."""
    adj = rules.adjustments(spec(), [{"reasonKey": "noSlot"}])
    assert [a["key"] for a in adj] == ["day", "weekend", "lunch"]
    assert adj[0]["patch"] == {"dayStart": "08:00"}
    assert rules.adjustments(spec(dayStart="07:00"), [{"reasonKey": "noSlot"}])[0]["patch"] == {"dayEnd": "19:00"}
    assert rules.adjustments(spec(), [{"reasonKey": "overdue"}]) == []


def test_daily_totals():
    tot = rules.daily_totals([TUE], [{"date": TUE, "minutes": 300, "taskType": "study"}], [])
    assert tot == [{"date": TUE, "minutes": 300, "newMinutes": 300, "studyMinutes": 300, "keptMinutes": 0}]


def test_performance_7_days_30_tasks():
    """9절 — 7일 × 작업 30건 배치 계산 100ms 이내 (공부 채우기 포함)."""
    evs = []
    for i in range(7):
        d = (NOW.date() + timedelta(days=i)).isoformat()
        evs += [cls(d, "09:00", "10:15", f"A{i}"), cls(d, "10:30", "11:45", f"B{i}"), cls(d, "13:00", "14:15", f"C{i}")]
        evs.append(todo(100 + i, d))
    items = [task(f"dl:{i}", f"과제{i}", (NOW + timedelta(days=1 + i % 6)).isoformat(), 1 + i % 4, slack=i) for i in range(23)]
    exams = [exam(f"ex:{i}", f"과목{i}", (NOW.date() + timedelta(days=3 + i)).isoformat(), 10 * i) for i in range(8)]
    t0 = time.perf_counter()
    res = run(evs, items, exams, spec(useWeekend=True))
    assert (time.perf_counter() - t0) < 0.1
    assert res["blocks"] and res["study"]
