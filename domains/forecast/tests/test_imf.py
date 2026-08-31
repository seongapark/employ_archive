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


def test_report_url_builds_the_weo_issue_address():
    # 실제로 200 을 확인한 주소다(설계 3.2)
    assert imf.report_url("April 2026", date(2026, 4, 14)) == (
        "https://www.imf.org/en/publications/weo/issues/"
        "2026/04/14/world-economic-outlook-april-2026"
    )
    assert imf.report_url("October 2025", date(2025, 10, 14)) == (
        "https://www.imf.org/en/publications/weo/issues/"
        "2025/10/14/world-economic-outlook-october-2025"
    )


def test_report_url_marks_an_update_issue():
    # Update 회차는 슬러그에 -update- 가 들어간다
    assert imf.report_url("Update July 2026", date(2026, 7, 8)) == (
        "https://www.imf.org/en/publications/weo/issues/"
        "2026/07/08/world-economic-outlook-update-july-2026"
    )


def test_report_url_rejects_a_label_it_cannot_read():
    # 월 이름을 못 읽으면 조용히 이상한 주소를 만들지 않는다
    with pytest.raises(ValueError, match="회차 라벨"):
        imf.report_url("Spring 2026", date(2026, 4, 14))


def test_no_record_points_at_a_machine_endpoint():
    # 설계 3.0 — 원문 보기가 JSON 을 띄우면 안 된다
    records = imf.parse("NGDP_RPCH", PAYLOAD, TODAY)
    assert records
    for r in records:
        for url in (r.source_url, r.landing_url):
            assert "api." not in url and "/api/" not in url and "sdmx" not in url
            assert url.startswith("https://www.imf.org/en/publications/weo/issues/")


def test_edition_with_label_returns_the_label_next_to_its_edition():
    assert imf.edition_with_label(2031) == ("April 2026", imf.EDITIONS["April 2026"])


def test_edition_with_label_refuses_to_pick_between_two_matches(monkeypatch):
    # 두 회차가 같은 전망 지평을 가지면(예: 지평을 늘리지 않는 10월판이 늘어나면)
    # 어느 쪽인지 고를 근거가 없다 — 조용히 하나를 고르지 않고 실패해야 한다.
    monkeypatch.setitem(
        imf.EDITIONS, "October 2026",
        ("IMF World Economic Outlook, October 2026", date(2026, 10, 13), 2031),
    )
    with pytest.raises(ValueError, match="여럿"):
        imf.edition_with_label(2031)


def test_parse_vintage_does_not_confuse_the_label_with_the_title():
    # collect_vintage 는 label 과 title 을 나란히 parse_vintage 에 넘긴다 — 둘 다
    # 평범한 문자열이라 자리가 바뀌어도 타입 오류 없이 조용히 통과할 수 있다.
    # source_url 은 label 로, report_title 은 title 로 지어야 함을 값으로 못박는다.
    flow, title, published_at = imf.VINTAGES["October 2025"]
    xml = '<Obs OBS_VALUE="1.8" TIME_PERIOD="2025"/><Obs OBS_VALUE="2.1" TIME_PERIOD="2026"/>'
    records = imf.parse_vintage(xml, "NGDP_RPCH", "October 2025", title, published_at)
    assert records
    expected_url = imf.report_url("October 2025", published_at)
    for r in records:
        assert r.source_url == expected_url
        assert r.landing_url == expected_url
        assert r.report_title == title
        for url in (r.source_url, r.landing_url):
            assert "api." not in url and "/api/" not in url and "sdmx" not in url
            assert url.startswith("https://www.imf.org/en/publications/weo/issues/")
