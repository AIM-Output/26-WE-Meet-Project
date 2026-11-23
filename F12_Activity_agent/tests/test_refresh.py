"""규칙 판이 바뀐 뒤 첫 목록 — 다시 뽑기(refresh)는 한 요청만 하고 짧게 나눠 저장한다 (2026-11-23).

예전에는 목록 요청이 공지 600건을 다시 뽑는 15초 동안 쓰기 잠금을 잡아, 같이 들어온 상태 확인이 'database is locked' 로 실패했다.
"""
import sqlite3
import threading
import time

from conftest import TODAY, add_notice

from activity import config as C
from activity import service, store

OPEN = "신청기간 : 2026. 10. 1. ~ 2026. 10. 20.(화) 18:00\n신청방법 : 이메일 접수"


def _stale(n: int) -> None:
    with store.connect() as con:
        for i in range(n):
            add_notice(con, f"www:{100 + i}", f"[모집공고] 2026 테스트 프로그램 {i}기 참가자 모집", OPEN)
        con.execute("UPDATE notices SET extract_ver = 0")


def test_refresh_once_in_short_commits_while_others_wait(profile, monkeypatch):
    import scholarship.store as base_store
    _stale(30)
    calls: list[str] = []
    real = service._build

    def slow_build(row):                                    # 공지 하나 0.03초 — 30건이면 0.9초 동안 다시 뽑는다
        calls.append(row["id"])
        time.sleep(0.03)
        return real(row)

    monkeypatch.setattr(service, "_build", slow_build)
    monkeypatch.setattr(base_store, "REFRESH_COMMIT_SEC", 0.1)
    out: dict[str, object] = {}

    def run(name: str) -> None:
        try:
            with store.connect() as con:
                out[name] = len(service.evaluate(con, profile, TODAY))
        except Exception as e:                              # noqa: BLE001 — 실패도 결과로 본다
            out[name] = e

    a = threading.Thread(target=run, args=("list",))        # 목록 요청
    b = threading.Thread(target=run, args=("status",))      # 같이 들어온 상태 확인
    a.start()
    time.sleep(0.1)
    b.start()
    time.sleep(0.2)
    # 다시 뽑는 중에도 다른 쓰기(수집기·진행 상태 바꾸기)가 0.5초 안에 들어간다 — 예전에는 0.9초 내내 막혔다
    other = sqlite3.connect(C.DB_PATH, timeout=0.5)
    try:
        other.execute("INSERT INTO meta(key, value) VALUES ('probe', '1')")
        other.commit()
    finally:
        other.close()
    a.join(10)
    b.join(10)
    assert out == {"list": 30, "status": 30}
    assert len(calls) == 30                                 # 같은 공지를 두 요청이 두 번 뽑지 않는다
    with store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM notices WHERE extract_ver < ?", (C.EXTRACT_VERSION,)).fetchone()[0] == 0
        assert service.refresh(con) == 0                    # 다 뽑은 뒤에는 할 일이 없다


def test_refresh_skips_inside_a_write_and_rows_still_read(profile):
    """이미 쓰는 중(트랜잭션)인 연결에서는 한꺼번에 뽑지 않는다 — 그 요청은 공지마다 뽑아 보여 준다."""
    _stale(3)
    with store.connect() as con:
        store.put_state(con, "www:100", note="쓰는 중")
        assert con.in_transaction and service.refresh(con) == 0
        assert len(service.evaluate(con, profile, TODAY)) == 3
    with store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM notices WHERE extract_ver < ?", (C.EXTRACT_VERSION,)).fetchone()[0] == 0
