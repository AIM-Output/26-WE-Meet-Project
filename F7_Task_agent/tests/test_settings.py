"""설정 (F7-R05 · S08) — 기본값과 다른 값만 저장 · null 은 기본값으로 · 범위 밖은 거절 · 깨진 파일에도 죽지 않는다."""
import json

import pytest

from tasks import config as C
from tasks import settings as S


def test_defaults_when_nothing_saved():
    v = S.view()
    # 2026-10-06 사용자 요청 기본값: 안전계수 1.0 · 과제 2시간 · 퀴즈 30분 · 동영상 50분 · 프로젝트 4시간
    assert v["safetyFactor"] == 1.0 and v["bedTime"] == "24:00"
    assert v["defaultHours"] == {"assignment": 2.0, "quiz": 0.5, "video": 50 / 60, "project": 4.0}
    assert v["changed"] == []
    assert [k["label"] for k in v["kinds"]] == ["과제", "퀴즈", "동영상", "프로젝트"]


def test_only_differences_are_stored():
    v = S.save({"safetyFactor": 2, "defaultHours": {"quiz": 0.5, "project": 8}, "bedTime": "24:00"})
    assert json.loads(C.SETTINGS_FILE.read_text(encoding="utf-8")) == {"safetyFactor": 2.0,
                                                                       "defaultHours": {"project": 8.0}}
    assert set(v["changed"]) == {"safetyFactor", "defaultHours.project"}


def test_partial_patch_keeps_other_values():
    S.save({"defaultHours": {"project": 8}})
    S.save({"defaultHours": {"quiz": 1}})
    assert S.load()["defaultHours"]["project"] == 8 and S.load()["defaultHours"]["quiz"] == 1


def test_null_resets_one_value_and_reset_all():
    S.save({"safetyFactor": 2, "bedTime": "01:00"})
    S.save({"safetyFactor": None})
    assert S.load()["safetyFactor"] == 1.0 and S.load()["bedTime"] == "01:00"
    S.save({}, reset=True)
    assert S.load() == C.default_settings()


def test_modal_values_equal_to_defaults_are_not_stored():
    """화면 칸은 동영상 50분을 0.83 으로 보인다 — 그대로 저장해도 기본값이라 파일에 남지 않고 '고친 칸'도 아니다."""
    v = S.save({"safetyFactor": 1, "defaultHours": {"assignment": 2, "quiz": 0.5, "video": 0.83, "project": 4},
                "bedTime": "24:00"})
    assert json.loads(C.SETTINGS_FILE.read_text(encoding="utf-8")) == {}
    assert v["changed"] == [] and v["defaultHours"]["video"] == 50 / 60


@pytest.mark.parametrize("value, stored", [("24:00", "24:00"), ("00:00", "24:00"), ("23:30", "23:30"),
                                           ("1:30", "01:30"), ("05:00", "05:00")])
def test_bed_time_normalised(value, stored):
    assert S.save({"bedTime": value})["bedTime"] == stored


@pytest.mark.parametrize("patch", [
    {"safetyFactor": 0.5}, {"safetyFactor": "많이"}, {"defaultHours": {"quiz": 0}},
    {"defaultHours": {"essay": 2}}, {"bedTime": "17:00"}, {"bedTime": "06:00"}, {"bedTime": "25:00"},
    {"bedTime": "abc"}, {"color": "red"},
])
def test_invalid_values_are_rejected(patch):
    with pytest.raises(S.Invalid):
        S.save(patch)
    assert S.load() == C.default_settings()


def test_corrupt_file_falls_back_per_field():
    C.DATA_DIR.mkdir(parents=True, exist_ok=True)
    C.SETTINGS_FILE.write_text(json.dumps({"safetyFactor": "x", "defaultHours": {"quiz": 2, "video": -1},
                                           "bedTime": "99:99"}), encoding="utf-8")
    s = S.load()
    assert s["safetyFactor"] == 1.0 and s["bedTime"] == "24:00"
    assert s["defaultHours"]["quiz"] == 2 and s["defaultHours"]["video"] == 50 / 60
    C.SETTINGS_FILE.write_text("{깨진 json", encoding="utf-8")
    assert S.load() == C.default_settings()
