"""가져오기 작업의 배관 — 종료 코드별 처리 · 저장 · 프로필 넘기기 · 성적 파일 삭제.
실제 학사정보시스템에는 접속하지 않는다 (subprocess.run 을 가짜로 바꾼다)."""
import json
import subprocess

import pytest

from graduation import config as C, jobs, service, store

DOC = {"fetchedAt": "2026-09-28T10:00:00",
       "courses": [{"year": 2024, "semester": "1", "rawCategory": "전필", "code": "CIS3001", "name": "자료구조",
                    "grade": "A0", "credits": 3.0}],
       "profile": {"gpa": {"value": 3.5, "scale": 4.5, "basis": "전체"}, "earned_credits": 3}}


@pytest.fixture()
def fake_run(monkeypatch, db):
    calls = {}

    def install(code: int, doc=DOC):
        def run(cmd, **kw):
            calls["cmd"] = cmd
            if code == 0:
                C.IMPORT_OUT.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            return subprocess.CompletedProcess(cmd, code)
        monkeypatch.setattr(jobs.subprocess, "run", run)
        return calls
    yield install
    jobs.on_profile = None
    jobs.on_change = None
    with jobs._lock:
        jobs._state["import"].update(running=False, startedAt=None)


def test_import_ok_saves_courses_and_hands_profile_to_c2(fake_run):
    calls = fake_run(0)
    got = {}
    jobs.on_profile = lambda p: got.update(p) or {"changed": ["gpa"]}
    st = jobs.run_import_blocking()
    assert st["ok"] and st["result"]["count"] == 1 and st["result"]["profile"] == {"changed": ["gpa"]}
    assert got["gpa"]["value"] == 3.5
    assert calls["cmd"][3:5] == ["-m", "graduation.hakstd"]
    assert not C.IMPORT_OUT.exists()                              # 성적이 담긴 파일은 남기지 않는다
    with store.connect() as con:
        assert [c["name"] for c in service.load_courses(con)] == ["자료구조"]


def test_import_login_required(fake_run):
    fake_run(2)
    st = jobs.run_import_blocking()
    assert st["ok"] is False and st["needLogin"]


def test_import_format_change_keeps_previous_courses(fake_run):
    with store.connect() as con:
        service.apply_import(con, DOC["courses"])
    fake_run(1)
    st = jobs.run_import_blocking()
    assert st["ok"] is False and "형식 변경" in st["error"]
    with store.connect() as con:
        assert len(service.load_courses(con)) == 1                # 이전 이수 내역은 그대로


def test_profile_callback_failure_does_not_undo_courses(fake_run):
    fake_run(0)

    def boom(_):
        raise RuntimeError("C2 가 잠겨 있음")
    jobs.on_profile = boom
    st = jobs.run_import_blocking()
    assert st["ok"] and "error" in st["result"]["profile"]
