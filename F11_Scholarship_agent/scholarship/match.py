"""판정 — 자격 요건(extract) × 프로필(C2) → 해당 / 확인 필요 / 비해당 / 마감 / 대상 아님 + 조건별 근거. 표준 라이브러리만.

원칙 (요구사항정의서 F11 4-다·5절, notice_agent/scripts/match.py 에서 옮김)
  - LLM 을 부르지 않는다. 같은 입력 → 항상 같은 출력. 판정마다 근거: "평점 3.0 이상 — 내 3.42 충족".
  - 프로필에 없는 값은 '모름'이지 '미달'이 아니다 → 확인 필요. 민감정보가 모자라면 그 칸에 sensitive 를 붙여
    화면이 그 자리에서 입력을 받게 한다 (F11-R30).
  - 평점 척도가 다르면(4.5 vs 4.3) 임의로 환산하지 않고 모름 (F11-R23).
  - 추출 신뢰도가 문턱 미만이면 결과가 어떻든 확인 필요 (F11-R13) — 놓치는 것이 잘못 알리는 것보다 나쁘다.
  - 사용자가 뒤집은 판정이 이긴다. 근거 목록은 그대로 둔다 (F11-R25·R26).
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from . import config as C
from . import registry
from .textutil import days_until, nfkc, to_date

VERDICT_LABEL = {"eligible": "해당", "needs_review": "확인 필요", "ineligible": "비해당", "expired": "마감",
                 "not_applicable": "대상 아님"}


def _r(field: str, label: str, status: str, message: str, *, need: Optional[str] = None, mine=None,
       evidence: Optional[str] = None, sensitive: Optional[str] = None, sure: bool = False) -> dict:
    """sure = 공지 본문을 못 읽어도(이미지·첨부 HWP) 믿을 수 있는 미달 — 제목의 [지역 재단]·단과대학·캠퍼스."""
    return {"field": field, "label": label, "status": status, "message": message, "need": need,
            "mine": mine, "evidence": evidence, "sensitive": sensitive, "sure": sure}


def _gpa_text(g: Optional[dict]) -> Optional[str]:
    return f"{g['value']:g}/{g['scale']:g}" if g else None


def _gpa_on_scale(p: dict, target: dict) -> tuple[Optional[float], str, Optional[str]]:
    """(내 값, 이유, 표시) — 척도가 다르면 None. 백분위(100점) 요건은 프로필에 백분위가 없어 모름."""
    last = (target.get("basis") or "").startswith("직전")
    g = (p.get("lastSemesterGpa") if last else None) or p.get("gpa")
    label = "직전 학기" if last and p.get("lastSemesterGpa") else "전체"
    if g is None:
        return None, f"{'직전 학기 ' if last else ''}평점이 프로필에 없습니다", None
    if float(target["scale"]) == 100:
        return None, f"백분위(100점) 기준 — 내 평점 {_gpa_text(g)} 은 학교 환산표로 확인하세요", _gpa_text(g)
    if abs(float(g["scale"]) - float(target["scale"])) > 1e-6:
        return None, f"척도가 다릅니다 (요건 {target['scale']:g} 만점 · 내 평점 {g['scale']:g} 만점) — 임의로 환산하지 않습니다", _gpa_text(g)
    return float(g["value"]), label, _gpa_text(g)


def reasons_for(req: dict, p: dict, notice: Optional[dict] = None) -> list[dict]:
    ev = req.get("evidence") or {}
    out: list[dict] = []
    if req.get("grades"):
        allowed = sorted(set(req["grades"]))
        need = ",".join(map(str, allowed)) + "학년"
        g = p.get("grade")
        if g is None:
            out.append(_r("grades", "학년", "unknown", f"{need} — 프로필에 학년이 없습니다", need=need, evidence=ev.get("grades")))
        else:
            ok = g in allowed
            out.append(_r("grades", "학년", "pass" if ok else "fail", f"{need} — 내 {g}학년 {'충족' if ok else '미달'}",
                          need=need, mine=f"{g}학년", evidence=ev.get("grades")))
    if req.get("minSemesters") is not None:
        need = f"{req['minSemesters']}학기 이상"
        s = p.get("semestersCompleted")
        if s is None:
            out.append(_r("minSemesters", "이수 학기", "unknown", f"{need} — 프로필에 이수 학기가 없습니다", need=need,
                          evidence=ev.get("minSemesters")))
        else:
            ok = s >= req["minSemesters"]
            out.append(_r("minSemesters", "이수 학기", "pass" if ok else "fail", f"{need} — 내 {s}학기 {'충족' if ok else '미달'}",
                          need=need, mine=f"{s}학기", evidence=ev.get("minSemesters")))
    if req.get("minGpa"):
        t = req["minGpa"]
        need = f"{t['value']:g}/{t['scale']:g} 이상" + (f" ({t['basis']})" if t.get("basis") else "")
        val, why, shown = _gpa_on_scale(p, t)
        if val is None:
            out.append(_r("minGpa", "평점", "unknown", f"{need} — {why}", need=need, mine=shown, evidence=ev.get("minGpa")))
        else:
            ok = val + 1e-9 >= t["value"]
            out.append(_r("minGpa", "평점", "pass" if ok else "fail", f"{need} — 내 {why} {val:g} {'충족' if ok else '미달'}",
                          need=need, mine=shown, evidence=ev.get("minGpa")))
    for key, label, pkey in (("minCredits", "누적 이수학점", "earnedCredits"), ("minCreditsLast", "직전 학기 이수학점", "lastSemesterCredits")):
        if req.get(key) is None:
            continue
        need = f"{req[key]}학점 이상"
        v = p.get(pkey)
        if v is None and key == "minCreditsLast" and p.get("earnedCredits") is not None and p.get("semestersCompleted"):
            v = None                     # 학기 평균으로 짐작하지 않는다
        if v is None:
            out.append(_r(key, label, "unknown", f"{need} — 프로필에 {label}이 없습니다", need=need, evidence=ev.get(key)))
        else:
            ok = v >= req[key]
            out.append(_r(key, label, "pass" if ok else "fail", f"{need} — 내 {v}학점 {'충족' if ok else '미달'}",
                          need=need, mine=f"{v}학점", evidence=ev.get(key)))
    if req.get("enrollment"):
        need = "/".join(req["enrollment"])
        st = p.get("enrollmentStatus")
        if not st:
            out.append(_r("enrollment", "학적", "unknown", f"{need} — 프로필에 학적이 없습니다", need=need, evidence=ev.get("enrollment")))
        else:
            ok = st in req["enrollment"]
            out.append(_r("enrollment", "학적", "pass" if ok else "fail", f"{need} — 내 학적 {st}", need=need, mine=st,
                          evidence=ev.get("enrollment")))
    if req.get("incomeMax") is not None:
        need = f"{req['incomeMax']}구간 이하"
        ib = p.get("incomeBracket")
        if ib is None:
            out.append(_r("incomeMax", "학자금 지원구간", "unknown", f"{need} — 지원구간을 넣으면 판정합니다 (한국장학재단에서 확인)",
                          need=need, evidence=ev.get("incomeMax"), sensitive="incomeBracket"))
        else:
            ok = ib <= req["incomeMax"]
            out.append(_r("incomeMax", "학자금 지원구간", "pass" if ok else "fail", f"{need} — 내 {ib}구간 {'충족' if ok else '미달'}",
                          need=need, mine=f"{ib}구간", evidence=ev.get("incomeMax"), sensitive="incomeBracket"))
    reg = req.get("residency")
    if reg:
        out.append(_residency(reg, p, ev.get("residency")))
    if req.get("fields"):
        need = "·".join(req["fields"]) + " 계열"
        mine = registry.fields_of(p)
        if not mine:
            out.append(_r("fields", "계열", "unknown", f"{need} — 내 학과의 계열을 알 수 없습니다", need=need, evidence=ev.get("fields")))
        else:
            ok = bool(set(mine) & set(req["fields"]))
            from_title = nfkc(ev.get("fields") or "").strip() == nfkc((notice or {}).get("title") or "").strip()
            out.append(_r("fields", "계열", "pass" if ok else "fail", f"{need} — 내 학과 {'·'.join(mine)} {'충족' if ok else '다름'}",
                          need=need, mine="·".join(mine), evidence=ev.get("fields"), sure=not ok and from_title))
    if req.get("colleges"):
        need = "·".join(req["colleges"])
        mine = p.get("college")
        if not mine:
            out.append(_r("colleges", "소속 단과대학", "unknown", f"{need} 학생 대상 — 프로필에 소속이 없습니다", need=need,
                          evidence=ev.get("colleges")))
        else:
            ok = any(registry.norm(c) == registry.norm(mine) for c in req["colleges"])
            out.append(_r("colleges", "소속 단과대학", "pass" if ok else "fail", f"{need} 학생 대상 — 내 소속 {mine}",
                          need=need, mine=mine, evidence=ev.get("colleges"), sure=not ok))
    if req.get("campus"):
        mine = registry.campus_of(p)
        need = f"{req['campus']}캠퍼스"
        if not mine:
            out.append(_r("campus", "캠퍼스", "unknown", f"{need} 학생 대상 — 프로필에 소속이 없습니다", need=need, evidence=ev.get("campus")))
        else:
            ok = mine == req["campus"]
            out.append(_r("campus", "캠퍼스", "pass" if ok else "fail", f"{need} 학생 대상 — 내 캠퍼스 {mine}", need=need,
                          mine=f"{mine}캠퍼스", evidence=ev.get("campus"), sure=not ok))
    if req.get("groups"):
        out.append(_groups(req["groups"], p, ev.get("groups"), bool(req.get("groupsSure"))))
    if req.get("nationality"):
        # 프로필(C2)은 국적을 묻지 않는다 — 국내 학부생 대부분이 해당하므로 막지 않되 근거는 남긴다
        out.append(_r("nationality", "국적", "pass", f"{req['nationality']} 국적 — 프로필에 국적이 없어 대한민국 국적으로 봅니다",
                      need=req["nationality"], mine="(묻지 않음)", evidence=ev.get("nationality")))
    unit = (notice or {}).get("unit")
    if unit and (unit.get("audience") or {}).get("scope") in ("related", "campus"):
        rel = registry.relevance(unit, p)
        if rel["level"] in ("related", "campus"):
            out.append(_r("unit", "주관 사업단", "pass", f"{unit['org']} — {rel['why']}", need=unit["org"],
                          mine=p.get("department") or p.get("college")))
        elif rel["level"] in ("open", "other"):
            out.append(_r("unit", "주관 사업단", "unknown", f"{unit['org']} — {rel['why']}. 참여 학생 대상인지 원문을 확인하세요",
                          need=unit["org"], mine=p.get("department") or p.get("college")))
    for c in (req.get("otherConditions") or [])[:6]:
        out.append(_r("other", "기타 조건", "unknown", f"자동 판정하지 않는 조건: {c[:100]}", need=c[:100], evidence=c))
    for x in (req.get("exclusions") or [])[:4]:
        out.append(_r("exclusion", "제외 사유", "unknown", f"제외 대상이 아닌지 확인: {x[:100]}", need=x[:100], evidence=x))
    return out


def _residency(reg: dict, p: dict, quote: Optional[str]) -> dict:
    """지역 장학 — 시·도가 맞으면 충족(시·군 단위면 본인 확인), 다르면 미달.
    지역 장학은 '본인·부모 주소' 또는 '그 지역 고교 출신' 둘 중 하나인 경우가 많다 → 거주지만 다르고 출신 고교를 모르면
    미달로 단정하지 않고 출신 고교 지역을 묻는다. 본문 근거가 '주소·거주'만 말하면(출신 말이 없으면) 거주지로 단정한다."""
    need = "·".join(reg.get("names") or reg["provinces"]) + (" (시·군)" if reg.get("level") == "city" else "")
    provs = set(reg["provinces"])
    home, school = p.get("residenceRegion"), p.get("highSchoolRegion")
    mine = " / ".join(x for x in (f"거주 {home}" if home else "", f"출신고 {school}" if school else "") if x) or None
    hits = [x for x in (home, school) if x and x in provs]
    body_lines = reg.get("bodyLines") or []
    says_school = bool(reg.get("mentionsSchool"))
    if body_lines:
        quote = body_lines[0]                               # 화면 근거는 본문의 조건 줄이 제목보다 낫다
    if hits:
        if reg.get("level") == "city":
            return _r("residency", "지역", "unknown", f"{need} — 같은 시·도({hits[0]})입니다. 시·군 단위 조건은 본인이 확인하세요",
                      need=need, mine=mine, evidence=quote, sensitive="residenceRegion")
        return _r("residency", "지역", "pass", f"{need} — 내 {mine} 충족 (주소·출신고 중 어느 기준인지 원문 확인)",
                  need=need, mine=mine, evidence=quote, sensitive="residenceRegion")
    if home and (school or (body_lines and not says_school)):
        return _r("residency", "지역", "fail", f"{need} 지역 장학 — 내 {mine} 와 다릅니다", need=need, mine=mine,
                  evidence=quote, sensitive="residenceRegion", sure=True)
    if home:
        return _r("residency", "지역", "unknown", f"{need} 지역 장학 — 거주({home})는 다릅니다. 출신 고교 기준일 수 있어 "
                  "출신 고교 지역을 넣으면 판정합니다", need=need, mine=mine, evidence=quote, sensitive="highSchoolRegion")
    return _r("residency", "지역", "unknown", f"{need} 지역 장학 — 거주 지역을 넣으면 판정합니다", need=need, mine=mine,
              evidence=quote, sensitive="residenceRegion")


def _groups(groups: list[dict], p: dict, quote: Optional[str], sure: bool) -> dict:
    need = "·".join(g["label"] for g in groups)
    flags = p.get("flags")
    checkable = [g for g in groups if g.get("profileKey")]
    income = any(g["label"] == "저소득층" for g in groups)
    if isinstance(flags, dict) and any(flags.get(g["profileKey"]) for g in checkable):
        hit = next(g["label"] for g in checkable if flags.get(g["profileKey"]))
        return _r("groups", "대상", "pass", f"{need} 대상 — 내 해당 사항 '{hit}'", need=need, mine=hit, evidence=quote, sensitive="flags")
    if isinstance(flags, dict) and checkable and len(checkable) == len(groups):
        if sure:
            return _r("groups", "대상", "fail", f"{need} 대상 — 내 해당 사항에 없습니다", need=need, mine="해당 없음",
                      evidence=quote, sensitive="flags", sure=True)
        return _r("groups", "대상", "unknown", f"{need} 대상이 있는 공지 — 내 해당 사항에는 없습니다. 다른 유형도 있는지 원문 확인",
                  need=need, mine="해당 없음", evidence=quote, sensitive="flags")
    if income and p.get("incomeBracket") is None:
        return _r("groups", "대상", "unknown", f"{need} 대상 — 학자금 지원구간을 넣으면 판정에 씁니다", need=need, evidence=quote,
                  sensitive="incomeBracket")
    if checkable and not isinstance(flags, dict):
        return _r("groups", "대상", "unknown", f"{need} 대상 — 해당 사항을 넣으면 판정합니다", need=need, evidence=quote,
                  sensitive="flags")
    return _r("groups", "대상", "unknown", f"{need} 대상인지 본인이 확인하세요", need=need, evidence=quote)


def decide(req: dict, profile: Optional[dict], notice: Optional[dict] = None, today: Optional[date] = None,
           override: Optional[dict] = None) -> dict:
    """→ {verdict, systemVerdict, label, reasons, unknown, sensitive, deadline, daysLeft, confidence, hint, flipped}.
    notice = {isResult, postedAt, unit, catalog} · override = 사용자가 뒤집은 판정 {verdict, reason, at}."""
    today = today or date.today()
    p = profile or {}
    n = notice or {}
    reasons = reasons_for(req, p, n)
    period = req.get("period") or {}
    deadline = period.get("end")
    left = days_until(deadline, today) if deadline else None
    fails = [r for r in reasons if r["status"] == "fail"]
    sure_fails = [r for r in fails if r.get("sure")]
    unknown = [r for r in reasons if r["status"] == "unknown"]
    conf = float(req.get("confidence") or 0)
    posted = to_date(n.get("postedAt"))
    stale = (not deadline and posted is not None and not n.get("catalog")
             and (today - posted).days > C.NO_PERIOD_STALE_DAYS)

    head: Optional[dict] = None
    if n.get("isResult"):
        verdict, head = "not_applicable", _r("notice", "공지 종류", "unknown", "선발 결과·명단 공지 — 신청하는 공지가 아닙니다")
    elif req.get("infoOnly"):
        verdict, head = "not_applicable", _r("notice", "공지 종류", "unknown", "홍보·안내 공지 — 신청하는 장학이 아닙니다")
    elif req.get("gradOnly"):
        verdict, head = "not_applicable", _r("audience", "대상", "fail", "대학원생 대상 — 학부생 대상이 아닙니다", need="대학원생")
    elif req.get("foreignOnly"):
        verdict, head = "not_applicable", _r("audience", "대상", "unknown", "외국인 유학생 대상 공지입니다", need="외국인 유학생")
    elif deadline and left is not None and left < 0 and (conf >= C.CONFIDENCE_THRESHOLD or left < -C.RECENT_EXPIRY_DAYS):
        verdict, head = "expired", _r("deadline", "신청 기간", "fail", f"신청 마감 지남 ({deadline[:16].replace('T', ' ')})",
                                      need=period.get("raw"), evidence=period.get("raw"))
    elif deadline and left is not None and left < 0:
        verdict, head = "needs_review", _r("deadline", "신청 기간", "unknown",
                                           f"마감이 지났을 수 있습니다 ({deadline[:10]}) — 원문 확인", evidence=period.get("raw"))
    elif stale:
        verdict, head = "expired", _r("deadline", "신청 기간", "unknown",
                                      f"신청 기간을 읽지 못한 지난 공지 (게시 {posted.isoformat()})")
    elif sure_fails:
        verdict = "ineligible"           # 본문을 못 읽었어도 제목의 지역 재단·단과대학·캠퍼스가 내 것이 아니면 확실하다
    elif req.get("needsOcr"):
        verdict, head = "needs_review", _r("extraction", "공지 읽기", "unknown", "본문이 이미지라 자동으로 판정하지 못했습니다 — 원문 확인")
    elif fails:
        verdict = "ineligible"
    elif conf < C.CONFIDENCE_THRESHOLD:
        verdict, head = "needs_review", _r("extraction", "공지 읽기", "unknown",
                                           "조건을 다 읽었는지 확신이 없어 자동 판정을 보류했습니다"
                                           + (" (첨부를 읽지 못함)" if req.get("attachmentsUnread") else ""))
    elif unknown:
        verdict = "needs_review"
    else:
        verdict = "eligible"
    if head:
        reasons.insert(0, head)

    hint = None
    if verdict == "needs_review":
        if any(r.get("sensitive") and r["status"] == "unknown" for r in reasons):
            hint = "정보 입력 필요"
        elif not fails and all(r["field"] in ("other", "exclusion", "unit", "extraction", "nationality") for r in unknown):
            hint = "조건 충족 추정" if req.get("structured") else "원문 확인"
        else:
            hint = "원문 확인"
    system = verdict
    flipped = False
    if override and override.get("verdict") in ("eligible", "ineligible"):
        verdict = override["verdict"]
        flipped = verdict != system
    return {
        "verdict": verdict, "systemVerdict": system, "label": VERDICT_LABEL[verdict], "flipped": flipped,
        "reasons": reasons, "unknown": list(dict.fromkeys(r["field"] for r in reasons if r["status"] == "unknown")),
        "sensitive": list(dict.fromkeys(r["sensitive"] for r in reasons if r.get("sensitive") and r["status"] == "unknown")),
        "failCount": len(fails), "deadline": deadline, "daysLeft": left, "confidence": conf, "hint": hint,
        "warning": "조건 미달 항목이 있습니다" if flipped and verdict == "eligible" and fails else None,
    }
