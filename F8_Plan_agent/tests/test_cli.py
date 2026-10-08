"""명령줄 — 다른 기능 폴더가 없어도 멈추지 않고 problems 에 적는다."""
from placement import __main__ as cli
from placement import sources


def test_preview_without_other_agents(capsys):
    sources.problems.clear()
    assert cli.main(["preview"]) == 0
    out = capsys.readouterr()
    assert "공강 배치 미리보기" in out.out and "수업이 없습니다" in out.out
    assert any("F3" in p for p in sources.problems)


def test_settings_command(capsys):
    assert cli.main(["settings", "--day", "08:00-18:00", "--weekend", "on", "--study", "off"]) == 0
    out = capsys.readouterr().out
    assert "08:00 ~ 18:00" in out and "주말 사용     켬" in out and "하루 상한     없음" in out and "안 만듦" in out
    assert cli.main(["settings", "--day", "09:00-21:00"]) == 2


def test_list_and_clear_empty(capsys):
    assert cli.main(["list"]) == 0
    assert cli.main(["clear"]) == 0
    assert "지웠습니다" in capsys.readouterr().out
