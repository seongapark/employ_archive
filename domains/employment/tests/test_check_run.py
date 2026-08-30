import json
from datetime import date

import pytest

from domains.employment.pipeline import check_run

TODAY = date(2026, 8, 30)
KDI_UNTIL_SEP = {"kdi": date(2026, 9, 30)}


def write_run(tmp_path, collectors, errors):
    path = tmp_path / "last_run.json"
    path.write_text(json.dumps({
        "run_at": "2026-08-30T16:00:00+09:00",
        "collectors": collectors,
        "conflicts": [],
        "errors": errors,
    }, ensure_ascii=False), encoding="utf-8")
    return path


def judge(path, known_down=KDI_UNTIL_SEP, today=TODAY):
    return check_run.main(path, known_down=known_down, today=today)


def test_passes_when_every_collector_succeeded(tmp_path):
    assert judge(write_run(tmp_path, {"bok": {"ok": True}}, []), known_down={}) == 0


def test_fails_on_an_error_nobody_expected(tmp_path, capsys):
    path = write_run(tmp_path, {"bok": {"ok": False}},
                     ["bok: ValueError: 요약표 페이지를 찾지 못했다"])
    assert judge(path) == 1
    assert "::error::bok: ValueError" in capsys.readouterr().out


def test_passes_while_a_known_outage_is_still_within_its_deadline(tmp_path, capsys):
    path = write_run(tmp_path, {"kdi": {"ok": False}},
                     ["kdi: HTTPError: HTTP Error 502: Bad Gateway"])
    assert judge(path) == 0
    assert "kdi: HTTPError" in capsys.readouterr().out


def test_suppression_holds_on_the_deadline_day_itself(tmp_path):
    path = write_run(tmp_path, {"kdi": {"ok": False}}, ["kdi: HTTPError: 502"])
    assert judge(path, today=date(2026, 9, 30)) == 0


def test_fails_once_the_deadline_has_passed(tmp_path, capsys):
    # 장애가 안 끝나도 언젠가 다시 들여다보게 만든다 — 유예가 영구 면제가 되면 안 된다
    path = write_run(tmp_path, {"kdi": {"ok": False}}, ["kdi: HTTPError: 502"])
    assert judge(path, today=date(2026, 10, 1)) == 1
    assert "유예" in capsys.readouterr().out


def test_still_fails_when_a_known_outage_hides_a_real_break(tmp_path):
    path = write_run(tmp_path, {"kdi": {"ok": False}, "bok": {"ok": False}}, [
        "kdi: HTTPError: HTTP Error 502: Bad Gateway",
        "bok: ValueError: 요약표 페이지를 찾지 못했다",
    ])
    assert judge(path) == 1


def test_fails_when_a_known_outage_recovers_so_the_entry_gets_removed(tmp_path, capsys):
    # 초록 실행에 붙은 경고는 아무도 안 본다. 목록에 남은 채 잊히면
    # 그 수집기가 조용히 빠져도 모르므로, 지울 때까지 빨갛게 둔다.
    path = write_run(tmp_path, {"kdi": {"ok": True}}, [])
    assert judge(path) == 1
    out = capsys.readouterr().out
    assert "::error::" in out and "KNOWN_DOWN" in out


def test_parses_entries_with_their_deadline():
    assert check_run.parse_known_down(" kdi@2026-09-30 , bok@2026-12-01 ") == {
        "kdi": date(2026, 9, 30), "bok": date(2026, 12, 1),
    }
    assert check_run.parse_known_down("") == {}


def test_rejects_an_entry_without_a_deadline():
    # 기한 없는 유예는 그대로 굳는다
    with pytest.raises(ValueError):
        check_run.parse_known_down("kdi")


def test_rejects_an_unreadable_deadline():
    with pytest.raises(ValueError):
        check_run.parse_known_down("kdi@언젠가")


def test_fails_loudly_when_the_known_down_list_is_malformed(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("KNOWN_DOWN", "kdi")
    path = write_run(tmp_path, {"kdi": {"ok": False}}, ["kdi: HTTPError: 502"])
    assert check_run.main(path, today=TODAY) == 1
    assert "::error::" in capsys.readouterr().out


def run_entry_point(path, **env_over):
    import os
    import subprocess
    import sys

    return subprocess.run(
        [sys.executable, "-m", "domains.employment.pipeline.check_run", str(path)],
        env={**os.environ, "KNOWN_DOWN": "kdi@2099-01-01", **env_over},
        capture_output=True, text=True, encoding="utf-8",
    )


def test_entry_point_judges_the_file_named_on_the_command_line(tmp_path):
    path = write_run(tmp_path, {"bok": {"ok": False}},
                     ["bok: ValueError: 요약표 페이지를 찾지 못했다"])
    proc = run_entry_point(path)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "::error::bok" in proc.stdout


def test_entry_point_prints_on_a_console_that_is_not_utf8(tmp_path):
    # 워크플로는 UTF-8 이지만 로컬 콘솔은 아닐 수 있다(윈도우 cp949).
    # 화면에 쓰다 터지면 판정 자체가 실패로 둔갑한다.
    path = write_run(tmp_path, {"kdi": {"ok": False}},
                     ["kdi: HTTPError: HTTP Error 502: Bad Gateway"])
    proc = run_entry_point(path, PYTHONIOENCODING="ascii")
    assert proc.returncode == 0, proc.stdout + proc.stderr
