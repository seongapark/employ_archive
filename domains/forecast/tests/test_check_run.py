import json
from datetime import date

import pytest

from domains.forecast.pipeline import check_run

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
        [sys.executable, "-m", "domains.forecast.pipeline.check_run", str(path)],
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


# ---------------------------------------------------------------------------
# 최종 검토 Fix 6 — 근거 실패는 경고다. 수치 실패만 판정을 바꾼다.
# ---------------------------------------------------------------------------

def write_run_with_rationale_errors(tmp_path, collectors, errors, rationale_errors):
    path = tmp_path / "last_run.json"
    path.write_text(json.dumps({
        "run_at": "2026-08-30T16:00:00+09:00",
        "collectors": collectors,
        "conflicts": [],
        "errors": errors,
        "rationale_errors": rationale_errors,
    }, ensure_ascii=False), encoding="utf-8")
    return path


def test_a_rationale_failure_alone_keeps_the_run_green(tmp_path, capsys):
    # 이게 이 수정의 요점이다. 예전엔 이 오류가 errors 에 섞여 있어
    # "keis" 의 수치 장애로 읽혔고, KNOWN_DOWN 으로 유예를 주면 이번엔
    # collectors["keis"]["ok"] 가 True 라 두 번째 루프에 걸렸다 — 두 갈래
    # 어디로 가도 빨갛고 안내문은 다시 첫 갈래로 보냈다.
    path = write_run_with_rationale_errors(
        tmp_path, {"keis": {"ok": True}}, [],
        ["keis: 근거 ValueError: 본문을 못 받았다"])
    assert judge(path, known_down={}) == 0
    out = capsys.readouterr().out
    assert "::warning::" in out
    assert "keis" in out
    assert "::error::" not in out


def test_a_rationale_failure_does_not_need_a_known_down_reprieve(tmp_path, capsys):
    # 유예를 주는 순간 예전 구현이 걸리던 그 두 번째 루프를 직접 자극한다 —
    # 수치는 성공(ok=True)인데 이름이 KNOWN_DOWN 에 있는 상태다. 근거
    # 실패에는 애초에 유예가 필요 없어야 한다.
    path = write_run_with_rationale_errors(
        tmp_path, {"keis": {"ok": True}}, [],
        ["keis: 근거 ValueError: 본문을 못 받았다"])
    assert judge(path, known_down={"keis": date(2026, 12, 31)}) == 1
    # 이때 빨간 이유는 근거가 아니라 "되살아난 수집기가 목록에 남아 있다"
    # 여야 한다 — 근거 쪽은 여전히 경고로만 찍힌다.
    out = capsys.readouterr().out
    assert "KNOWN_DOWN" in out
    assert "::warning::" in out


def test_a_numbers_failure_still_fails_even_beside_a_rationale_warning(tmp_path, capsys):
    # 근거 칸을 새로 만들었다고 수치 판정이 무뎌지면 안 된다.
    path = write_run_with_rationale_errors(
        tmp_path, {"bok": {"ok": False}, "keis": {"ok": True}},
        ["bok: ValueError: 요약표 페이지를 찾지 못했다"],
        ["keis: 근거 ValueError: 본문을 못 받았다"])
    assert judge(path, known_down={}) == 1
    out = capsys.readouterr().out
    assert "::error::bok" in out
    assert "::warning::" in out


def test_an_old_last_run_without_the_new_key_is_still_judged(tmp_path):
    # 이 브랜치 이전에 쓰인 last_run.json 에는 rationale_errors 키가 없다 —
    # KeyError 로 터지면 옛 실행을 다시 판정할 수 없게 된다.
    assert judge(write_run(tmp_path, {"bok": {"ok": True}}, []), known_down={}) == 0
