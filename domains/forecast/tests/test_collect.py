import json
from datetime import date, datetime
from domains.forecast.pipeline.models import ForecastRecord, make_id
from domains.forecast.pipeline import collect, store


def fake_record(value: float, pub: date) -> ForecastRecord:
    return ForecastRecord(
        id=make_id("OECD", pub, "gdp_growth", 2027), org="OECD", org_name_ko="OECD",
        report_title="test", published_at=pub, target_year=2027,
        indicator="gdp_growth", value=value, unit="%",
        source_url="https://example.com/a", landing_url="https://example.com",
        confidence="verified", collected_at=datetime(2026, 8, 29, 16, 0),
    )


def test_main_saves_new_records_and_last_run(tmp_path):
    collectors = {"fake": lambda today: [fake_record(2.0, today)]}
    rc = collect.main(data_dir=tmp_path, collectors=collectors)
    assert rc == 0
    saved = store.load_forecasts(tmp_path / "forecasts.json")
    assert len(saved) == 1
    summary = json.loads((tmp_path / "last_run.json").read_text(encoding="utf-8"))
    assert summary["collectors"]["fake"]["ok"] is True
    assert summary["collectors"]["fake"]["added"] == 1


def test_main_skips_unchanged_values(tmp_path):
    collectors = {"fake": lambda today: [fake_record(2.0, today)]}
    collect.main(data_dir=tmp_path, collectors=collectors)
    collect.main(data_dir=tmp_path, collectors=collectors)  # 같은 값 재수집
    saved = store.load_forecasts(tmp_path / "forecasts.json")
    assert len(saved) == 1  # 값이 안 바뀌었으므로 신규 레코드 없음


def test_main_records_collector_failure_and_continues(tmp_path):
    def boom(today):
        raise RuntimeError("site down")

    collectors = {
        "bad": boom,
        "good": lambda today: [fake_record(2.0, today)],
    }
    rc = collect.main(data_dir=tmp_path, collectors=collectors)
    assert rc == 0  # 부분 실패해도 나머지는 저장
    saved = store.load_forecasts(tmp_path / "forecasts.json")
    assert len(saved) == 1
    summary = json.loads((tmp_path / "last_run.json").read_text(encoding="utf-8"))
    assert summary["collectors"]["bad"]["ok"] is False
    assert len(summary["errors"]) == 1
