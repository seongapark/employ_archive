import json
from datetime import date, datetime
from pathlib import Path

from domains.employment.pipeline import collect
from domains.employment.pipeline.models import SeriesRecord, make_id


def rec(source="ei", period="2026-07", value=15877.0):
    return SeriesRecord(
        id=make_id(source, period, "total", None), source=source,
        breakdown="total", category=None, period=period, value=value, yoy=1.0,
        released_at=date(2026, 8, 11), release_url="https://x/view",
        collected_at=datetime(2026, 8, 30, 9, 0),
    )


def test_writes_records_and_a_run_summary(tmp_path):
    code = collect.main(tmp_path, {"ei": lambda today: [rec()]})
    assert code == 0
    rows = json.loads((tmp_path / "series.json").read_text(encoding="utf-8"))
    assert [r["id"] for r in rows] == ["ei-2026-07-headcount-total"]
    summary = json.loads((tmp_path / "last_run.json").read_text(encoding="utf-8"))
    assert summary["collectors"]["ei"]["ok"] is True
    assert summary["errors"] == []


def test_one_broken_collector_does_not_stop_the_others(tmp_path):
    def boom(today):
        raise ValueError("표를 찾지 못했다")

    collect.main(tmp_path, {"ei": boom, "est": lambda today: [rec(source="est")]})
    summary = json.loads((tmp_path / "last_run.json").read_text(encoding="utf-8"))
    assert summary["collectors"]["ei"]["ok"] is False
    assert summary["collectors"]["est"]["ok"] is True
    assert summary["errors"] == ["ei: ValueError: 표를 찾지 못했다"]


def test_the_summary_never_carries_a_traceback(tmp_path):
    def boom(today):
        raise ValueError("실패")

    collect.main(tmp_path, {"ei": boom})
    text = (tmp_path / "last_run.json").read_text(encoding="utf-8")
    assert "Traceback" not in text and "File \"" not in text


def test_manual_entries_win_over_collected_ones(tmp_path):
    manual = tmp_path / "manual"
    manual.mkdir()
    override = rec(value=99999.0).model_dump(mode="json")
    (manual / "2026-07.json").write_text(
        json.dumps([override], ensure_ascii=False), encoding="utf-8")

    collect.main(tmp_path, {"ei": lambda today: [rec(value=15877.0)]})
    rows = json.loads((tmp_path / "series.json").read_text(encoding="utf-8"))
    assert rows[0]["value"] == 99999.0


def test_revised_values_replace_the_old_ones(tmp_path):
    collect.main(tmp_path, {"ei": lambda today: [rec(period="2026-06", value=15855.0)]})
    collect.main(tmp_path, {"ei": lambda today: [rec(period="2026-06", value=15856.0)]})
    rows = json.loads((tmp_path / "series.json").read_text(encoding="utf-8"))
    assert len(rows) == 1
    assert rows[0]["value"] == 15856.0
