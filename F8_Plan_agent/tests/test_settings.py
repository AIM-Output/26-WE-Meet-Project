"""가용 시간 설정 — F8-S09 · 6절. 기본값과 다른 값만 저장한다."""
import json

import pytest

from placement import config as C
from placement import settings as S


def test_defaults():
    """2026-10-07 사용자 요청 — 낮 09:00~18:00 만 (저녁은 F5 계획 몫) · 하루 상한 없음 · 남는 공강은 공부."""
    v = S.view()
    assert (v["dayStart"], v["dayEnd"]) == ("09:00", "18:00")
    assert "eveningStart" not in v and "dailyMaxHours" not in v and v["changed"] == []
    assert v["bufferMinutes"] == 10 and v["minSlotMinutes"] == 30 and v["maxBlockMinutes"] == 120
    assert v["useWeekend"] is False and v["fillStudy"] is True and v["lunchBreak"] and v["rangeDays"] == 7


def test_save_only_changed_values():
    S.save({"dayStart": "08:00", "dayEnd": "18:00", "useWeekend": False})
    assert json.loads(C.SETTINGS_FILE.read_text(encoding="utf-8")) == {"dayStart": "08:00"}
    assert S.view()["changed"] == ["dayStart"]


def test_null_resets_one_and_reset_all():
    S.save({"dayStart": "08:00", "bufferMinutes": 15})
    S.save({"dayStart": None})
    assert S.load()["dayStart"] == "09:00" and S.load()["bufferMinutes"] == 15
    S.save({}, reset=True)
    assert S.stored() is None


@pytest.mark.parametrize("patch", [
    {"dayStart": "06:00"},                  # 07:00 보다 이르다
    {"dayEnd": "20:00"},                    # 19:00 뒤는 저녁 — F5 계획 몫
    {"dayEnd": "24:00"},
    {"dayStart": "17:50"},                  # 끝까지 30분이 안 된다
    {"eveningStart": "19:00"},              # 2026-10-07 에 F5 로 옮긴 설정
    {"useClassGaps": True},                 # 없앤 설정 (낮 범위 안은 전부 공강)
    {"fillStudy": "yes"},
    {"bufferMinutes": 7},
    {"rangeDays": 10},
    {"minSlotMinutes": 90, "maxBlockMinutes": 60},
    {"useWeekend": "yes"},
    {"lunchStart": "13:00", "lunchEnd": "12:00"},
    {"maxBlockMinutes": 1.5},
    {"dailyMaxHours": 4},                   # 없앤 설정
])
def test_invalid(patch):
    with pytest.raises(S.Invalid):
        S.save(patch)


def test_broken_file_falls_back():
    C.ensure_dirs()
    C.SETTINGS_FILE.write_text('{"dayStart": "nope", "bufferMinutes": 15, "eveningStart": "18:00"}', encoding="utf-8")
    v = S.load()
    assert v["dayStart"] == "09:00" and v["bufferMinutes"] == 15 and "eveningStart" not in v


def test_merged_does_not_save():
    m = S.merged({"useWeekend": False})
    assert m["useWeekend"] is False and S.stored() is None
