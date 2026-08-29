from datetime import date
from domains.forecast.pipeline.collectors import imf

TODAY = date(2026, 8, 29)

PAYLOAD = {
    "values": {
        "NGDP_RPCH": {
            "KOR": {"2024": 2.0, "2025": 0.9, "2026": 1.8, "2027": 2.1, "2028": 2.2}
        }
    }
}


def test_parse_picks_current_and_next_year():
    records = imf.parse("NGDP_RPCH", PAYLOAD, TODAY)
    got = {r.target_year: r for r in records}
    assert set(got) == {2026, 2027}
    assert got[2026].value == 1.8
    assert got[2027].value == 2.1


def test_parse_record_fields():
    r = imf.parse("NGDP_RPCH", PAYLOAD, TODAY)[0]
    assert r.org == "IMF"
    assert r.indicator == "gdp_growth"
    assert r.id.startswith("imf-2026-08-gdp_growth-")
    assert r.confidence == "verified"
    assert r.unit == "%"


def test_parse_missing_years_returns_partial():
    payload = {"values": {"LUR": {"KOR": {"2026": 3.1}}}}
    records = imf.parse("LUR", payload, TODAY)
    assert len(records) == 1
    assert records[0].indicator == "unemp_rate"
    assert records[0].target_year == 2026


def test_parse_empty_payload_returns_nothing():
    assert imf.parse("PCPIPCH", {"values": {}}, TODAY) == []
