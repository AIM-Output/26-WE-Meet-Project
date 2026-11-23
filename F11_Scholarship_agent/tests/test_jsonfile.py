"""설정 JSON 읽기(jsonfile) · 장학 다시 뽑기(refresh) — 2026-11-23.

원천 사전을 찾을 때마다 파일 시각을 보던 것(대외활동 목록 한 번에 stat 3만 5천 번, Windows 6초)을 2초에 한 번으로 줄였다.
"""
import json
import os
import time

from conftest import TODAY, add_notice

from scholarship import config as C
from scholarship import jsonfile, service, store


class CountingPath:
    """stat 을 센다 — 비교는 실제 경로로 (JsonFile 이 경로가 바뀌었는지 볼 때)."""

    def __init__(self, real):
        self.real, self.stats = real, 0

    def stat(self):
        self.stats += 1
        return self.real.stat()

    def read_text(self, encoding):
        return self.real.read_text(encoding=encoding)

    def __eq__(self, other):
        return isinstance(other, CountingPath) and other.real == self.real


def test_jsonfile_checks_mtime_once_per_window_and_reloads(tmp_path, monkeypatch):
    f = tmp_path / "a.json"
    f.write_text(json.dumps({"v": 1}), encoding="utf-8")
    p = CountingPath(f)
    jf = jsonfile.JsonFile(lambda: p, prepare=lambda d: d["v"] * 10)
    for _ in range(1000):
        assert jf.get() == {"v": 1}
    assert p.stats == 1 and jf.extra() == 10                # 공지마다 불러도 파일 시각은 한 번만 본다
    f.write_text(json.dumps({"v": 2}), encoding="utf-8")
    os.utime(f, (time.time() + 5, time.time() + 5))
    assert jf.get() == {"v": 1}                             # 2초 안에는 예전 내용
    monkeypatch.setattr(jsonfile, "RECHECK_SEC", 0)
    assert jf.get() == {"v": 2} and jf.extra() == 20        # 다시 볼 때가 되면 바뀐 내용
    monkeypatch.setattr(jsonfile, "RECHECK_SEC", 60)
    q = CountingPath(tmp_path / "b.json")
    q.real.write_text(json.dumps({"v": 3}), encoding="utf-8")
    path = [p]
    jf2 = jsonfile.JsonFile(lambda: path[0])
    assert jf2.get() == {"v": 2}
    path[0] = q
    assert jf2.get() == {"v": 3}                            # 경로가 바뀌면(설정·테스트) 기다리지 않고 바로


def test_refresh_reextracts_stale_once(profile):
    with store.connect() as con:
        for i in range(4):
            add_notice(con, f"www:{i}", f"[장학안내] 2026 테스트 장학 {i}차 선발", "신청기간 : 2026. 10. 1. ~ 2026. 10. 30.")
        con.execute("UPDATE notices SET extract_ver = 0")
    with store.connect() as con:
        assert service.refresh(con) == 4 and service.refresh(con) == 0
        assert {r[0] for r in con.execute("SELECT extract_ver FROM notices")} == {C.EXTRACT_VERSION}
        con.execute("UPDATE notices SET extract_ver = 0")
        store.put_state(con, "www:1", note="쓰는 중")       # 쓰는 중인 연결에서는 한꺼번에 뽑지 않는다
        assert service.refresh(con) == 0
        assert len([i for i in service.evaluate(con, profile, TODAY) if i["kind"] == "notice"]) == 4
