from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from domains.forecast.pipeline.collectors import oecd

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = (FIXTURES / "oecd_eo119_kor.csv").read_text(encoding="utf-8")
EO118 = (FIXTURES / "oecd_eo118_kor.csv").read_text(encoding="utf-8")
SERIALS_HTML = (FIXTURES / "oecd_serials.html").read_text(encoding="utf-8")
TODAY = date(2026, 8, 29)


@pytest.fixture
def stub_report_url(monkeypatch):
    """report_url() 을 결정적인 값으로 채운다 — 네트워크 없이 parse() 만 확인하는
    테스트가 명시적으로 가져다 쓴다(autouse 로 전체에 걸면 report_url 자신의
    동작 — 연재 목록 조회, 없는 회차의 raise — 을 검증할 길이 없어진다). 그
    동작은 이 픽스처를 쓰지 않는 report_url 전용 테스트들이 직접 부른다."""
    monkeypatch.setattr(
        oecd, "report_url",
        lambda edition: f"https://www.oecd.org/en/publications/eo{edition}-en.html")


def by_key(records):
    return {(r.indicator, r.target_year): r for r in records}


@pytest.mark.usefixtures("stub_report_url")
def test_parse_maps_measures_and_rounds():
    got = by_key(oecd.parse(FIXTURE))
    assert got[("gdp_growth", 2026)].value == 2.6
    assert got[("gdp_growth", 2027)].value == 1.9
    assert got[("unemp_rate", 2026)].value == 2.8
    assert got[("cpi", 2027)].value == 2.2


@pytest.mark.usefixtures("stub_report_url")
def test_parse_derives_emp_change_from_et_levels():
    got = by_key(oecd.parse(FIXTURE))
    assert got[("emp_change", 2026)].value == 20.5  # (28974095.855-28769250)/1e4
    assert got[("emp_change", 2027)].value == 12.3
    assert got[("emp_change", 2026)].unit == "만명"


@pytest.mark.usefixtures("stub_report_url")
def test_parse_record_fields():
    r = by_key(oecd.parse(FIXTURE))[("gdp_growth", 2027)]
    assert r.id == "oecd-2026-06-gdp_growth-2027"
    assert r.report_title == "Economic Outlook 119"
    assert r.org == "OECD"
    assert r.confidence == "verified"
    assert r.published_at == date(2026, 6, 3)  # EO 119 발표일


@pytest.mark.usefixtures("stub_report_url")
def test_parse_covers_current_and_next_year_only():
    years = {r.target_year for r in oecd.parse(FIXTURE)}
    assert years == {2026, 2027}


@pytest.mark.usefixtures("stub_report_url")
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


@pytest.mark.usefixtures("stub_report_url")
def test_parse_stamps_the_edition_publication_date():
    got = by_key(oecd.parse(EO118))
    r = got[("gdp_growth", 2026)]
    assert r.published_at == date(2025, 12, 2)  # EO 118 발표일
    assert r.report_title == "Economic Outlook No 118"
    assert r.id == "oecd-2025-12-gdp_growth-2026"


@pytest.mark.usefixtures("stub_report_url")
def test_parse_reads_the_2026_forecast_of_the_earlier_edition():
    # 같은 2026년 전망이 회차마다 갱신된다 — 이 값이 수정 이력의 앞자리다
    assert by_key(oecd.parse(EO118))[("gdp_growth", 2026)].value == 2.1
    assert by_key(oecd.parse(FIXTURE))[("gdp_growth", 2026)].value == 2.6


@pytest.mark.usefixtures("stub_report_url")
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


def _stub_serials_listing(monkeypatch):
    # report_url() 이 http.get(SERIALS_URL) 로 목록을 긁는다. 실제 네트워크
    # 대신 실제 목록에서 딴 픽스처를 돌려준다 — report_url 의 몸통(목록 조회,
    # 소속 확인, raise)이 진짜로 실행되게 하려는 것이다. report_url 자체를
    # 갈아치우는 stub_report_url 픽스처로는 이 몸통을 한 번도 통과시키지
    # 못한다.
    monkeypatch.setattr(oecd.http, "get", lambda url, **kw: SimpleNamespace(text=SERIALS_HTML))


def test_report_url_resolves_an_edition_present_in_the_listing(monkeypatch):
    _stub_serials_listing(monkeypatch)
    assert oecd.report_url(119) == (
        "https://www.oecd.org/en/publications/"
        "oecd-economic-outlook-volume-2026-issue-1_2d1956f0-en.html"
    )


def test_report_url_raises_when_the_edition_is_absent_from_the_listing(monkeypatch):
    # 픽스처 목록은 2026년 1호(=EO 119)까지만 있다. EO 120 은 (2026, 2호)로
    # 매핑되는데 목록에 없다 — 옛 회차 주소나 LANDING_URL 로 떨어지지 않고
    # 실패해야 한다(설계 4장, 전역 제약).
    _stub_serials_listing(monkeypatch)
    with pytest.raises(ValueError, match="120") as exc_info:
        oecd.report_url(120)
    message = str(exc_info.value)
    assert oecd.LANDING_URL not in message
    assert "sdmx" not in message.lower()


def test_report_url_is_called_once_per_edition_not_once_per_record(monkeypatch):
    # report_url() 은 네트워크를 탄다. 회차 하나가 레코드 수십 개를 낳으므로
    # 레코드마다 부르면 요청도 그만큼 는다 — 이번 주 형제 수집기에서 실제로
    # 하루 요청이 1번에서 136번으로 는 회귀다. 호출 횟수를 직접 센다.
    calls = []

    def counting(edition):
        calls.append(edition)
        return f"https://www.oecd.org/en/publications/eo{edition}-en.html"

    monkeypatch.setattr(oecd, "report_url", counting)
    records = oecd.parse(FIXTURE)

    assert len(records) > 1  # 레코드가 하나뿐이면 이 테스트는 아무것도 증명하지 못한다
    assert calls == [119]
