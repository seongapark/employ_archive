from datetime import date, datetime
import pytest
from domains.forecast.pipeline.models import ForecastRecord, make_id, VALUE_RANGES, INDICATOR_META


def base_kwargs(**over):
    kw = dict(
        id="oecd-2026-08-gdp_growth-2027", org="OECD", org_name_ko="OECD",
        report_title="Economic Outlook 119", published_at=date(2026, 8, 29),
        target_year=2027, indicator="gdp_growth", value=1.9, unit="%",
        source_url="https://sdmx.oecd.org/example",
        landing_url="https://www.oecd.org/economic-outlook",
        confidence="verified", collected_at=datetime(2026, 8, 29, 16, 0),
    )
    kw.update(over)
    return kw


def test_valid_record_with_defaults():
    r = ForecastRecord(**base_kwargs())
    assert r.target_period == "annual"
    assert r.prev_value is None
    assert r.revision is None
    assert r.rationale == ""
    assert r.rationale_tags == []
    assert r.source_page is None


def test_value_out_of_range_rejected():
    with pytest.raises(ValueError):
        ForecastRecord(**base_kwargs(value=12.5))  # gdp_growth 범위는 -10~10


def test_unknown_indicator_rejected():
    with pytest.raises(ValueError):
        ForecastRecord(**base_kwargs(indicator="gdp"))


def test_make_id():
    assert make_id("OECD", date(2026, 8, 29), "gdp_growth", 2027) == \
        "oecd-2026-08-gdp_growth-2027"


def test_meta_loaded_from_indicators_json():
    assert set(VALUE_RANGES) == set(INDICATOR_META)
    assert VALUE_RANGES["gdp_growth"] == (-10, 10)
    assert INDICATOR_META["emp_change"]["unit"] == "만명"


def test_make_id_keeps_annual_ids_unchanged():
    assert make_id("BOK", date(2026, 8, 27), "emp_change", 2026, "annual") == \
        "bok-2026-08-emp_change-2026"


def test_make_id_separates_half_year_records():
    assert make_id("BOK", date(2026, 8, 27), "emp_change", 2026, "h1") == \
        "bok-2026-08-emp_change-2026-h1"
    assert make_id("BOK", date(2026, 8, 27), "emp_change", 2026, "h2") == \
        "bok-2026-08-emp_change-2026-h2"
