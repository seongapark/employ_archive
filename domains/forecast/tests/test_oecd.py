from datetime import date
from pathlib import Path

import pytest

from domains.forecast.pipeline.collectors import oecd

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = (FIXTURES / "oecd_eo119_kor.csv").read_text(encoding="utf-8")
EO118 = (FIXTURES / "oecd_eo118_kor.csv").read_text(encoding="utf-8")
SERIALS_HTML = (FIXTURES / "oecd_serials.html").read_text(encoding="utf-8")
TODAY = date(2026, 8, 29)


@pytest.fixture(autouse=True)
def _fake_report_url(monkeypatch):
    # report_url() 은 네트워크를 탄다 — parse() 를 부르는 테스트마다 실제
    # 연재 목록을 긁으면 매 실행이 느려지고 오프라인에서 깨진다. URL 조립
    # 자체를 검증하는 테스트(volume_issue·parse_serials·report_url 관련)는
    # 이 모듈이 아니라 실제 함수를 직접 부른다.
    monkeypatch.setattr(
        oecd, "report_url",
        lambda edition: f"https://www.oecd.org/en/publications/eo{edition}-en.html")


def by_key(records):
    return {(r.indicator, r.target_year): r for r in records}


def test_parse_maps_measures_and_rounds():
    got = by_key(oecd.parse(FIXTURE))
    assert got[("gdp_growth", 2026)].value == 2.6
    assert got[("gdp_growth", 2027)].value == 1.9
    assert got[("unemp_rate", 2026)].value == 2.8
    assert got[("cpi", 2027)].value == 2.2


def test_parse_derives_emp_change_from_et_levels():
    got = by_key(oecd.parse(FIXTURE))
    assert got[("emp_change", 2026)].value == 20.5  # (28974095.855-28769250)/1e4
    assert got[("emp_change", 2027)].value == 12.3
    assert got[("emp_change", 2026)].unit == "만명"


def test_parse_record_fields():
    r = by_key(oecd.parse(FIXTURE))[("gdp_growth", 2027)]
    assert r.id == "oecd-2026-06-gdp_growth-2027"
    assert r.report_title == "Economic Outlook 119"
    assert r.org == "OECD"
    assert r.confidence == "verified"
    assert r.published_at == date(2026, 6, 3)  # EO 119 발표일


def test_parse_covers_current_and_next_year_only():
    years = {r.target_year for r in oecd.parse(FIXTURE)}
    assert years == {2026, 2027}


def test_parse_skips_blank_obs_value():
    blank_row = (
        "DATAFLOW,OECD.ECO.MAD:DSD_EO@DF_EO(1.5),Economic Outlook 119,I,KOR,Korea,"
        "CPI_YTYPCT,Headline inflation,A,Annual,2026,,\n"
    )
    augmented = FIXTURE + blank_row
    got = by_key(oecd.parse(augmented))
    assert got[("gdp_growth", 2026)].value == 2.6
    assert got[("gdp_growth", 2027)].value == 1.9
    assert got[("unemp_rate", 2026)].value == 2.8
    assert got[("cpi", 2027)].value == 2.2
    assert got[("cpi", 2026)].value == 2.6  # unaffected by the blank row


def test_edition_number_reads_both_naming_styles():
    # 최신 데이터플로는 "Economic Outlook 119", 과거 회차는 "Economic Outlook No 118"
    assert oecd.edition_number("Economic Outlook 119") == 119
    assert oecd.edition_number("Economic Outlook No 118") == 118


def test_parse_stamps_the_edition_publication_date(): 
    got = by_key(oecd.parse(EO118))
    r = got[("gdp_growth", 2026)]
    assert r.published_at == date(2025, 12, 2)  # EO 118 발표일
    assert r.report_title == "Economic Outlook No 118"
    assert r.id == "oecd-2025-12-gdp_growth-2026"


def test_parse_reads_the_2026_forecast_of_the_earlier_edition():
    # 같은 2026년 전망이 회차마다 갱신된다 — 이 값이 수정 이력의 앞자리다
    assert by_key(oecd.parse(EO118))[("gdp_growth", 2026)].value == 2.1
    assert by_key(oecd.parse(FIXTURE))[("gdp_growth", 2026)].value == 2.6


def test_target_years_come_from_the_data_not_from_today():
    # 12월 회차는 다음 두 해를 전망한다. 수집일 기준으로 잡으면 어긋난다.
    assert {r.target_year for r in oecd.parse(EO118)} == {2026, 2027}


def test_parse_refuses_an_edition_whose_publication_date_is_unknown():
    # 새 회차가 나오면 발표일을 적어야 한다. 조용히 틀린 날짜를 쓰지 않는다.
    unknown = FIXTURE.replace("Economic Outlook 119", "Economic Outlook 120")
    with pytest.raises(ValueError, match="120"):
        oecd.parse(unknown)


def test_latest_edition_uses_the_undated_dataflow():
    # 최신 회차는 DF_EO 에 들어 있고 DF_EO_119 라는 데이터플로는 없다
    latest = max(oecd.EDITIONS)
    assert "DF_EO," in oecd._data_url(latest)
    assert f"DF_EO_{latest}" not in oecd._data_url(latest)
    assert f"DF_EO_{latest - 1}" in oecd._data_url(latest - 1)


def test_volume_issue_maps_the_edition_number():
    # 실제 대조로 확인한 대응이다(설계 3.3)
    assert oecd.volume_issue(116) == (2024, 2)
    assert oecd.volume_issue(117) == (2025, 1)
    assert oecd.volume_issue(118) == (2025, 2)
    assert oecd.volume_issue(119) == (2026, 1)
    assert oecd.volume_issue(120) == (2026, 2)


def test_parse_serials_reads_every_volume_issue():
    got = oecd.parse_serials(SERIALS_HTML)
    assert got[(2026, 1)] == (
        "https://www.oecd.org/en/publications/"
        "oecd-economic-outlook-volume-2026-issue-1_2d1956f0-en.html"
    )
    assert got[(2024, 2)].endswith("volume-2024-issue-2_d8814e8b-en.html")
    assert len(got) == 4


def test_parse_serials_raises_when_the_listing_has_none():
    with pytest.raises(ValueError, match="연재 목록"):
        oecd.parse_serials("<html><body>준비중</body></html>")


def test_no_record_points_at_a_machine_endpoint(monkeypatch):
    # 설계 3.0
    monkeypatch.setattr(oecd, "report_url",
                        lambda edition: "https://www.oecd.org/en/publications/x_1234abcd-en.html")
    records = oecd.parse(FIXTURE)
    assert records
    for r in records:
        for url in (r.source_url, r.landing_url):
            assert "sdmx" not in url and "/rest/data/" not in url
