import json

import pytest

from domains.forecast.pipeline import check_run


def write_run(tmp_path, collectors, errors):
    path = tmp_path / "last_run.json"
    path.write_text(json.dumps({
        "run_at": "2026-08-30T16:00:00+09:00",
        "collectors": collectors,
        "conflicts": [],
        "errors": errors,
    }, ensure_ascii=False), encoding="utf-8")
    return path


def test_passes_when_every_collector_succeeded(tmp_path):
    path = write_run(tmp_path, {"bok": {"ok": True}}, [])
    assert check_run.main(path, known_down=set()) == 0


def test_fails_on_an_error_nobody_expected(tmp_path, capsys):
    path = write_run(tmp_path, {"bok": {"ok": False}},
                     ["bok: ValueError: 요약표 페이지를 찾지 못했다"])
    assert check_run.main(path, known_down={"kdi"}) == 1
    assert "::error::bok: ValueError" in capsys.readouterr().out


def test_passes_when_only_a_known_outage_failed(tmp_path, capsys):
    path = write_run(tmp_path, {"kdi": {"ok": False}},
                     ["kdi: HTTPError: HTTP Error 502: Bad Gateway"])
    assert check_run.main(path, known_down={"kdi"}) == 0
    assert "kdi: HTTPError" in capsys.readouterr().out


def test_still_fails_when_a_known_outage_hides_a_real_break(tmp_path):
    path = write_run(tmp_path, {"kdi": {"ok": False}, "bok": {"ok": False}}, [
        "kdi: HTTPError: HTTP Error 502: Bad Gateway",
        "bok: ValueError: 요약표 페이지를 찾지 못했다",
    ])
    assert check_run.main(path, known_down={"kdi"}) == 1


def test_asks_to_clear_the_list_when_a_known_outage_recovers(tmp_path, capsys):
    # 목록에 남겨둔 채 잊으면 그 수집기가 조용히 빠져도 모른다
    path = write_run(tmp_path, {"kdi": {"ok": True}}, [])
    assert check_run.main(path, known_down={"kdi"}) == 0
    assert "::warning::" in capsys.readouterr().out


def test_reads_the_known_down_list_from_the_environment(monkeypatch):
    monkeypatch.setenv("KNOWN_DOWN", " kdi , bok ")
    assert check_run.known_down_from_env() == {"kdi", "bok"}
    monkeypatch.setenv("KNOWN_DOWN", "")
    assert check_run.known_down_from_env() == set()


def test_entry_point_prints_on_a_console_that_is_not_utf8(tmp_path):
    # 워크플로는 UTF-8 이지만 로컬 콘솔은 아닐 수 있다(윈도우 cp949).
    # 화면에 쓰다 터지면 판정 자체가 실패로 둔갑한다.
    import os
    import subprocess
    import sys

    path = write_run(tmp_path, {"kdi": {"ok": False}},
                     ["kdi: HTTPError: HTTP Error 502: Bad Gateway"])
    proc = subprocess.run(
        [sys.executable, "-m", "domains.forecast.pipeline.check_run", str(path)],
        env={**os.environ, "PYTHONIOENCODING": "ascii", "KNOWN_DOWN": "kdi"},
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
