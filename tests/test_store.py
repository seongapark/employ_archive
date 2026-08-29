from datetime import date, datetime
from src.models import ForecastRecord, make_id
from src import store


def rec(month: int, value: float, year: int = 2027, org: str = "OECD",
        indicator: str = "gdp_growth") -> ForecastRecord:
    pub = date(2026, month, 15)
    return ForecastRecord(
        id=make_id(org, pub, indicator, year), org=org, org_name_ko=org,
        report_title="test", published_at=pub, target_year=year,
        indicator=indicator, value=value, unit="%",
        source_url="https://example.com/a", landing_url="https://example.com",
        confidence="verified", collected_at=datetime(2026, month, 15, 16, 0),
    )


def test_first_insert_has_no_prev():
    result = store.merge([], [rec(6, 2.0)])
    assert result.added == ["oecd-2026-06-gdp_growth-2027"]
    assert result.records[0].prev_value is None
    assert result.records[0].revision is None


def test_second_edition_links_prev_and_revision():
    first = store.merge([], [rec(6, 2.0)]).records
    result = store.merge(first, [rec(8, 2.3)])
    added = [r for r in result.records if r.id == "oecd-2026-08-gdp_growth-2027"][0]
    assert added.prev_value == 2.0
    assert added.revision == 0.3


def test_same_id_same_value_skipped():
    first = store.merge([], [rec(6, 2.0)]).records
    result = store.merge(first, [rec(6, 2.0)])
    assert result.skipped == ["oecd-2026-06-gdp_growth-2027"]
    assert len(result.records) == 1


def test_same_id_different_value_is_conflict_not_overwrite():
    first = store.merge([], [rec(6, 2.0)]).records
    result = store.merge(first, [rec(6, 2.5)])
    assert len(result.conflicts) == 1
    assert result.records[0].value == 2.0  # 덮어쓰지 않음


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "forecasts.json"
    records = store.merge([], [rec(6, 2.0), rec(8, 2.3)]).records
    store.save_forecasts(path, records)
    loaded = store.load_forecasts(path)
    assert [r.id for r in loaded] == [r.id for r in records]
    assert loaded[1].prev_value == 2.0


def test_load_missing_file_returns_empty(tmp_path):
    assert store.load_forecasts(tmp_path / "nope.json") == []
