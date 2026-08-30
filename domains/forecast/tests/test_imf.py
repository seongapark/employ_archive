import pytest
from datetime import date
from domains.forecast.pipeline.collectors import imf

TODAY = date(2026, 8, 29)

PAYLOAD = {
    "values": {
        "NGDP_RPCH": {
            # 전망 지평(마지막 연도)이 회차를 특정한다 — 2031 = April 2026
            "KOR": {"2024": 2.0, "2025": 0.9, "2026": 1.8, "2027": 2.1, "2028": 2.2,
                    "2029": 2.2, "2030": 2.1, "2031": 2.1}
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
    assert r.id.startswith("imf-2026-04-gdp_growth-")  # 수집일이 아니라 발표일
    assert r.confidence == "verified"
    assert r.unit == "%"


def test_parse_missing_years_returns_partial():
    series = {str(y): 3.1 for y in range(2024, 2032)}
    del series["2027"]
    records = imf.parse("LUR", {"values": {"LUR": {"KOR": series}}}, TODAY)
    assert [r.target_year for r in records] == [2026]
    assert records[0].indicator == "unemp_rate"


def test_parse_empty_payload_returns_nothing():
    assert imf.parse("PCPIPCH", {"values": {}}, TODAY) == []


def payload(values):
    return {"values": {"NGDP_RPCH": {"KOR": values}}}


def test_edition_is_identified_by_the_forecast_horizon():
    # DataMapper 도 SDMX 도 어느 회차인지 밝히지 않는다. WEO 는 4월판마다 전망
    # 지평을 한 해 늘리므로, 마지막 연도로 회차를 특정한다.
    assert imf.edition_for_horizon(2031) == imf.EDITIONS["April 2026"]


def test_an_unknown_horizon_fails_loudly_instead_of_guessing_a_date():
    with pytest.raises(ValueError, match="EDITIONS"):
        imf.edition_for_horizon(2032)


def test_parse_stamps_the_edition_publication_date():
    data = payload({str(y): 1.0 for y in range(2000, 2032)})
    records = imf.parse("NGDP_RPCH", data, date(2026, 8, 30))
    assert records
    assert all(r.published_at == date(2026, 4, 14) for r in records)
    assert records[0].id.startswith("imf-2026-04-")
    assert records[0].report_title == "IMF World Economic Outlook, April 2026"


def test_parse_target_years_come_from_the_edition_not_from_today():
    data = payload({str(y): 1.0 for y in range(2000, 2032)})
    years = {r.target_year for r in imf.parse("NGDP_RPCH", data, date(2026, 8, 30))}
    assert years == {2026, 2027}
