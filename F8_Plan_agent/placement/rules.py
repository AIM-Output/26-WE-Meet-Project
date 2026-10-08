"""배치 규칙 — 순수 함수 (F8 5절 ②·③, F8-R10~R17 — 2026-10-07 개정).

낮 공강(기본 09:00~18:00)에 두 단계로 넣는다.

① 해야 할 것 — place(tasks, slots, settings)
  - assignment  F7 과제 — **마감 전 공강** 중 이른 곳부터(R11). 길이 = F7 필요 시간(예상 소요 × 안전계수).
  - todo        C1 할 일(날짜만 있는 미완료) — 그 날짜까지(지난 할 일은 기간 안 아무 때나). 길이 30분.
  순서: F7 이 준 순서 그대로(F7-R34). 할 일은 같은 잣대(여유 = 기한 − 지금 − 길이)로 그 사이에 끼운다.
      for 작업 in 순서:
          for 공강 in (기한 이전 · 이른 순):
              그 날 같은 작업 블록 ≥ 2개 → 다음 날로                (R16)
              넣을 길이 = min(남은 시간, 공강 길이, 최대 2시간)       (R13 · R14)
              자투리(< 최소 길이)가 남으면 그만큼 줄여 다음 블록이 받게 한다 (30분 단위)
          남으면 미배치 (이유)                                      (R17)

② 남는 공강 — fill_study(free, targets, settings)  (설정 fillStudy, 기본 켬)
  과제·할 일을 다 넣고 **남은 공강을 공부 블록으로 채운다**. 공강 하나를 앞에서부터 메우며, 매번 점수가 가장 높은 시험(과목)을 고른다.
      점수 = 남은 진도율(1 − 진도%) ÷ 시험까지 남은 날수(그 블록 날짜 기준, 시험 당일은 0.5일)
             × 0.5^(그 날 이미 넣은 같은 과목 블록 수)          ← 한 과목만 하루 종일 하지 않게
  진도 100% · 시험이 지난 · 같은 날 이미 2블록인 과목은 빼고, 시험 당일은 시험 시작 전(여유 포함)까지만.
  시각이 미정인 시험은 당일에 넣지 않는다. 동점이면 시험이 빠른 것 → 과목명 → id.

하루 상한은 없다 (2026-10-06 사용자 요청 — F8-R15 삭제). 하루 합계는 보여 주기만 한다.
같은 입력이면 같은 배치다(9절 정확성) — 정렬은 전부 안정 정렬이고 키 끝에 id 가 있다.
"""
from __future__ import annotations

import copy
from datetime import date, datetime
from typing import Optional

from . import config as C
from .settings import hhmm, minutes as to_min


# ---------------------------------------------------------------- 순서

def order(dated_tasks: list[dict], assignment_tasks: list[dict]) -> list[dict]:
    """F7 순서(그대로) 사이에 할 일을 여유 순으로 끼운다. 둘 다 `slack`(시간)을 가진다."""
    extra = sorted(dated_tasks, key=lambda t: (t["slack"], t.get("date") or "", t["title"], t["key"]))
    f7 = list(assignment_tasks)
    out: list[dict] = []
    i = j = 0
    while i < len(f7) and j < len(extra):
        if extra[j]["slack"] < (f7[i]["slack"] if f7[i]["slack"] is not None else float("inf")):
            out.append(extra[j])
            j += 1
        else:
            out.append(f7[i])
            i += 1
    return out + f7[i:] + extra[j:]


# ---------------------------------------------------------------- 문구

def _fmt_len(m: int) -> str:
    h, r = divmod(int(m), 60)
    return f"{h}시간 {r}분" if h and r else f"{h}시간" if h else f"{r}분"


def _md(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"{d.month}/{d.day}"


def reason_of(task: dict, slot_minutes: int, length: int) -> str:
    """블록 근거 한 줄 (F8-R22 · S03) — '소프트웨어공학론 · 10/2 18:00 마감 · 5시간 중 2시간 · 공강 60분'."""
    where = f"공강 {slot_minutes}분"
    if task["type"] == "todo":
        when = f"{_md(task['date'])} 할 일" + (" (밀린 할 일)" if task.get("late") else "")
        return f"{when} · {where}"
    due = task["due"]
    due_text = f"{due.month}/{due.day} {due.hour:02d}:{due.minute:02d} 마감"
    if (due.hour, due.minute) == (0, 0):                         # 자정 마감은 전날 24:00 (F6 자정 규칙)
        prev = date.fromordinal(due.date().toordinal() - 1)
        due_text = f"{prev.month}/{prev.day} 24:00 마감"
    part = f"{_fmt_len(task['totalMinutes'])} 중 {_fmt_len(length)}" if length < task["totalMinutes"] else _fmt_len(length)
    return f"{task['detail']} · {due_text} · {part} · {where}"


def _limit_of(task: dict, d: str) -> Optional[int]:
    """그 날 이 작업이 쓸 수 있는 마지막 분 — 기한(마감) 시각에서 자른다. None 이면 그 날을 쓸 수 없다."""
    due: datetime = task["due"]
    dd = due.date().isoformat()
    if d < dd:
        return C.DAY_END
    if d == dd:
        return due.hour * 60 + due.minute
    return None


def _block(task_key: str, task_type: str, title: str, d: str, start: int, length: int, slot: dict,
           reason: str, **extra) -> dict:
    return {
        "key": f"{task_key}|{d}|{hhmm(start)}", "taskType": task_type, "refId": task_key, "title": title,
        "date": d, "start": hhmm(start), "end": hhmm(start + length), "minutes": length,
        "slot": slot.get("source", "gap"), "slotMinutes": slot.get("orig", slot["minutes"]),
        "reason": reason, **extra,
    }


# ---------------------------------------------------------------- ① 과제 · 할 일

def place(tasks: list[dict], slots: dict[str, list[dict]], settings: dict,
          now: Optional[datetime] = None, range_end: Optional[str] = None) -> dict:
    """정렬된 작업 → 블록 · 미배치 · 미룸(마감이 기간 뒤라 다음 배치로) · 남은 공강(free).

    slots 는 {날짜: [{start, end, minutes, source}]} — 이 함수가 고치지 않는다(복사해서 쓴다)."""
    free = {d: [dict(s, orig=s["minutes"]) for s in v] for d, v in copy.deepcopy(slots).items()}
    days = sorted(free)
    range_end = range_end or (days[-1] if days else None)
    min_len, max_len = int(settings["minSlotMinutes"]), int(settings["maxBlockMinutes"])
    blocks: list[dict] = []
    unplaced: list[dict] = []
    deferred: list[dict] = []

    for task in tasks:
        remaining = int(task["minutes"])
        if remaining <= 0:
            continue
        if task["type"] == "assignment" and now is not None and task["due"] <= now:
            unplaced.append(_miss(task, remaining, "overdue"))
            continue
        need = min(min_len, int(task["totalMinutes"]))           # 원래 30분보다 짧은 작업(퀴즈 20분)은 그 길이로
        seen = short = same = False
        per_day: dict[str, int] = dict(task.get("keptPerDay") or {})    # 남겨 둔 같은 작업 블록도 센다 (R16)
        mine: list[dict] = []
        for d in days:
            limit = _limit_of(task, d)
            if limit is None:
                continue
            if remaining < need:                                    # 쪼개다 남은 자투리 — 혼자서는 블록이 못 된다
                short = True
                break
            day_full = False
            for s in free[d]:
                # 한 공강 안에서는 이어 붙인다 (연속 슬롯 우선 — 3시간 과제가 2시간 + 1시간)
                while remaining > 0 and not day_full:
                    if remaining < need:
                        short = True
                        break
                    avail = min(s["end"], limit) - s["start"]
                    if avail <= 0:
                        break
                    seen = True
                    if per_day.get(d, 0) >= C.MAX_BLOCKS_PER_TASK_PER_DAY:      # R16
                        same = same or avail >= need
                        day_full = True
                        break
                    if avail < need:
                        short = True
                        break
                    length = min(remaining, avail, max_len)
                    left = remaining - length
                    if 0 < left < need and length - (need - left) >= need:  # 자투리를 남기지 않게 줄인다
                        length -= need - left
                    start = s["start"]
                    mine.append(_block(task["key"], task["type"], task["title"], d, start, length, s,
                                       reason_of(task, s["orig"], length),
                                       course=task.get("course") or "", color=task.get("color") or C.STUDY_COLOR,
                                       href=task.get("href")))
                    s["start"] += length
                    s["minutes"] = s["end"] - s["start"]
                    per_day[d] = per_day.get(d, 0) + 1
                    remaining -= length
                if remaining <= 0 or day_full or remaining < need:
                    break
            free[d] = [s for s in free[d] if s["end"] - s["start"] > 0]
            if remaining <= 0:
                break
        n = len(mine)
        for i, b in enumerate(mine, 1):
            if n > 1:
                b["part"] = f"{i}/{n}"
        blocks += mine
        if remaining > 0:
            if task["type"] == "assignment" and range_end and task["due"].date().isoformat() > range_end:
                deferred.append({"refId": task["key"], "title": task["title"], "course": task.get("course") or "",
                                 "remainingMinutes": remaining, "due": task["due"].isoformat(timespec="minutes"),
                                 "text": f"마감이 기간 뒤라 {_fmt_len(remaining)}은 다음 배치로 넘깁니다"})
            else:
                why = "sameTask" if same else "short" if short else "noSlot"
                if not seen:
                    why = "noSlot"
                unplaced.append(_miss(task, remaining, why))

    blocks.sort(key=lambda b: (b["date"], b["start"], b["key"]))
    return {"blocks": blocks, "unplaced": unplaced, "deferred": deferred,
            "free": {d: [s for s in v if s["end"] - s["start"] > 0] for d, v in free.items()}}


def _miss(task: dict, remaining: int, why: str) -> dict:
    return {
        "refId": task["key"], "taskType": task["type"], "title": task["title"], "course": task.get("course") or "",
        "remainingMinutes": remaining, "totalMinutes": int(task["totalMinutes"]),
        "reasonKey": why, "reason": C.REASONS[why], "href": task.get("href"),
        "text": f"{task['title']} {_fmt_len(task['totalMinutes'])} 중 {_fmt_len(remaining)} — {C.REASONS[why]}",
    }


# ---------------------------------------------------------------- ② 남는 공강 → 공부 블록

def study_score(target: dict, d: date, same_day_count: int) -> float:
    """남은 진도율 ÷ 시험까지 남은 날수 × 0.5^(그 날 같은 과목 블록 수). 클수록 먼저."""
    remain = (100 - float(target.get("percent") or 0)) / 100
    days_left = max((date.fromisoformat(target["date"]) - d).days, C.STUDY_SAME_DAY_MIN_DAYS)
    return remain / days_left * (C.STUDY_REPEAT_PENALTY ** same_day_count)


def study_reason(target: dict, d: date, slot_minutes: int) -> str:
    """'남은 진도 85% · 시험 D-12 · 공강 60분' — 왜 이 과목인지가 보이게."""
    left = (date.fromisoformat(target["date"]) - d).days
    when = f"{target['time']} 시험 전" if left == 0 else f"시험 D-{left}"
    tail = " · 임의 일정" if target.get("isAuto") else ""
    return f"남은 진도 {100 - int(target.get('percent') or 0)}% · {when} · 공강 {slot_minutes}분{tail}"


def fill_study(free: dict[str, list[dict]], targets: list[dict], settings: dict,
               kept: Optional[dict[str, dict[str, int]]] = None) -> list[dict]:
    """과제·할 일을 넣고 남은 공강 → 공부 블록 (2026-10-07). free 는 고친다(채운 만큼 줄어든다).

    targets = [{examId, title, course, color, date, time, percent, href, isAuto}] (F5 study_targets 를 F8 모양으로)
    kept    = {examId: {날짜: 남겨 둔 블록 수}} — 하루 2블록 제한·같은 과목 감점에 같이 센다."""
    min_len, max_len = int(settings["minSlotMinutes"]), int(settings["maxBlockMinutes"])
    buf = int(settings["bufferMinutes"])
    cands = [t for t in targets if float(t.get("percent") or 0) < 100]
    counts: dict[str, dict[str, int]] = {t["examId"]: dict((kept or {}).get(t["examId"], {})) for t in cands}
    out: list[dict] = []
    for d in sorted(free):
        dd = date.fromisoformat(d)
        for s in sorted(free[d], key=lambda x: x["start"]):
            while s["end"] - s["start"] >= min_len:
                best, best_key, best_limit = None, None, 0
                for t in cands:
                    ed = date.fromisoformat(t["date"])
                    if dd > ed:
                        continue
                    limit = s["end"]
                    if dd == ed:                                    # 시험 당일 — 시험 시작 전(여유 포함)까지만
                        if not t.get("time"):
                            continue
                        limit = min(limit, to_min(t["time"]) - buf)
                    if limit - s["start"] < min_len:
                        continue
                    n = counts[t["examId"]].get(d, 0)
                    if n >= C.MAX_BLOCKS_PER_TASK_PER_DAY:
                        continue
                    key = (-study_score(t, dd, n), t["date"], t.get("course") or "", t["examId"])
                    if best_key is None or key < best_key:
                        best, best_key, best_limit = t, key, limit
                if best is None:
                    break
                avail = best_limit - s["start"]
                length = min(avail, max_len)
                left = (s["end"] - s["start"]) - length
                if 0 < left < min_len and length - (min_len - left) >= min_len:    # 공강 끝에 자투리를 남기지 않게
                    length -= min_len - left
                start = s["start"]
                out.append(_block(best["examId"], "study", best["title"], d, start, length, s,
                                  study_reason(best, dd, s.get("orig", s["minutes"])),
                                  course=best.get("course") or "", color=best.get("color") or C.STUDY_COLOR,
                                  href=best.get("href"), percent=best.get("percent"),
                                  examDate=best["date"], typeLabel=best.get("typeLabel") or ""))
                s["start"] += length
                s["minutes"] = s["end"] - s["start"]
                counts[best["examId"]][d] = counts[best["examId"]].get(d, 0) + 1
        free[d] = [s for s in free[d] if s["end"] - s["start"] > 0]
    return out


# ---------------------------------------------------------------- 합계 · 조정 제안

def daily_totals(days: list[str], blocks: list[dict], kept: list[dict]) -> list[dict]:
    """날짜별 합계 (F8-S06). 상한이 없으므로 overLimit 은 없다 — 보여 주기만 한다."""
    out = []
    for d in days:
        new = sum(b["minutes"] for b in blocks if b["date"] == d)
        study = sum(b["minutes"] for b in blocks if b["date"] == d and b["taskType"] == "study")
        old = sum(b["minutes"] for b in kept if b["date"] == d)
        out.append({"date": d, "minutes": new + old, "newMinutes": new, "studyMinutes": study, "keptMinutes": old})
    return out


def adjustments(settings: dict, unplaced: list[dict]) -> list[dict]:
    """미배치가 생기면 고칠 수 있는 설정 — 낮 시간 늘리기 · 주말 켜기 · 점심 시간도 쓰기.
    누르면 그 patch 를 저장하고 바로 다시 계산한다 (Frontend-Route 13-3). 저녁은 F5 몫이라 늘리지 않는다."""
    if not [u for u in unplaced if u["reasonKey"] not in ("overdue", "excluded")]:
        return []
    out = []
    ds, de = to_min(settings["dayStart"]), to_min(settings["dayEnd"])
    if ds - C.DAY_STEP_MINUTES >= to_min(C.DAY_EARLIEST):
        ns = hhmm(ds - C.DAY_STEP_MINUTES)
        out.append({"key": "day", "label": "낮 시간 늘리기", "text": f"{ns}부터 쓰기", "patch": {"dayStart": ns}})
    elif de + C.DAY_STEP_MINUTES <= to_min(C.DAY_LATEST):
        ne = hhmm(de + C.DAY_STEP_MINUTES)
        out.append({"key": "day", "label": "낮 시간 늘리기", "text": f"{ne}까지 쓰기", "patch": {"dayEnd": ne}})
    if not settings["useWeekend"]:
        out.append({"key": "weekend", "label": "주말 켜기", "text": "토·일 낮도 쓰기", "patch": {"useWeekend": True}})
    if settings["lunchBreak"]:
        out.append({"key": "lunch", "label": "점심 시간도 쓰기",
                    "text": f"{settings['lunchStart']}~{settings['lunchEnd']} 도 배치", "patch": {"lunchBreak": False}})
    return out[:3]
