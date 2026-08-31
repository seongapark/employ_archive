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


def test_a_broken_manual_file_does_not_discard_the_run(tmp_path):
    manual = tmp_path / "manual"
    manual.mkdir()
    (manual / "2026-07.json").write_text('[{"id": "oops"}]', encoding="utf-8")

    code = collect.main(tmp_path, {"ei": lambda today: [rec()]})

    assert code == 0
    rows = json.loads((tmp_path / "series.json").read_text(encoding="utf-8"))
    assert rows, "수집 결과가 버려졌다"
    summary = json.loads((tmp_path / "last_run.json").read_text(encoding="utf-8"))
    assert any(e.startswith("manual:") for e in summary["errors"])


def test_injected_collectors_mean_no_network(tmp_path, monkeypatch):
    """collectors 를 주입하는 테스트는 바깥 세상에 나가지 않겠다는 뜻이다.

    보도자료 색인과 KOSIS 대조가 collect 에 붙으면서 이 테스트들이 매번 게시판
    두 곳과 KOSIS 를 두드리게 됐다(11초 → 2분). 기본값이 꺼져 있는지 확인한다.
    """
    def boom(*a, **kw):
        raise AssertionError("테스트가 네트워크를 두드렸다")

    monkeypatch.setattr("domains.employment.pipeline.releases.refresh", boom)
    monkeypatch.setattr("domains.employment.pipeline.check_kosis.check", boom)
    code = collect.main(tmp_path, {"ei": lambda today: [rec()]})
    assert code == 0


def test_release_index_is_written_when_the_refresh_is_supplied(tmp_path):
    index = {"ei": {"2026-07": {"url": "https://x/1", "attachments": []}}}
    collect.main(tmp_path, {"ei": lambda today: [rec()]},
                 refresh_releases=lambda existing: (index, {"ei": {"months": 1}}))
    written = json.loads((tmp_path / "releases.json").read_text(encoding="utf-8"))
    assert written == index
    summary = json.loads((tmp_path / "last_run.json").read_text(encoding="utf-8"))
    assert summary["releases"]["ei"]["months"] == 1


def test_a_failing_table_check_is_an_error_not_a_crash(tmp_path):
    """KOSIS 표가 바뀌면 시끄럽게 남기되, 그날 숫자 수집은 살린다."""
    def mismatch(records):
        raise ValueError("KOSIS DT_1DA7002S 가 보도자료와 다르다")

    code = collect.main(tmp_path, {"ei": lambda today: [rec()]}, check_table=mismatch)
    assert code == 0
    summary = json.loads((tmp_path / "last_run.json").read_text(encoding="utf-8"))
    assert any("kosis_check" in e for e in summary["errors"])
    # 숫자는 그대로 저장됐다
    assert json.loads((tmp_path / "series.json").read_text(encoding="utf-8"))
