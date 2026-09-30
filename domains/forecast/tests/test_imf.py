import pytest
from datetime import date
from domains.forecast.pipeline.collectors import imf


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


def test_report_url_rejects_a_label_whose_month_disagrees_with_published_at():
    # 라벨의 월(4월)과 발표일의 월(10월)이 서로 다른 EDITIONS 행에서 온
    # 값처럼 어긋난다 — 조용히 4월 주소를 만들지 않고 멈춰야 한다
    with pytest.raises(ValueError, match="어긋난다"):
        imf.report_url("April 2026", date(2026, 10, 14))


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


def test_collect_vintage_passes_label_and_title_to_the_right_slot(monkeypatch):
    # 위 테스트는 parse_vintage 자체가 label/title 을 안 헷갈린다는 것만 본다 —
    # 실제 위험은 imf.py 안 호출부(collect_vintage 가 label, title 을 나란히
    # 넘기는 자리)다. 진짜 VINTAGES 항목은 label("October 2025")이 title 문자열
    # 안에 그대로 들어 있어(위 테스트가 쓰는 값) 자리가 바뀌어도 report_url 이
    # 우연히 같은 주소를 만들어낼 수 있다. 그래서 여기서는 label 에는 월 이름이
    # 있고 title 에는 없는 값으로 VINTAGES 를 바꿔 스와핑이 반드시 드러나게 한다.
    label = "October 2025"
    title = "가상의 WEO 과거 회차 표제"  # 월 이름이 없어 label 자리에 들어가면 report_url 이 바로 실패한다
    published_at = date(2025, 10, 14)
    monkeypatch.setitem(imf.VINTAGES, label, ("TEST_FLOW/1.0.0", title, published_at))
    monkeypatch.setattr(
        imf, "fetch_vintage",
        lambda flow, imf_code: (
            '<Obs OBS_VALUE="1.8" TIME_PERIOD="2025"/><Obs OBS_VALUE="2.1" TIME_PERIOD="2026"/>'
        ),
    )

    records = imf.collect_vintage(label)

    assert records
    expected_url = imf.report_url(label, published_at)
    for r in records:
        assert r.source_url == expected_url
        assert r.landing_url == expected_url
        assert r.report_title == title
        for url in (r.source_url, r.landing_url):
            assert "api." not in url and "/api/" not in url and "sdmx" not in url
            assert url.startswith("https://www.imf.org/en/publications/weo/issues/")


# ── 매일 수집: SDMX WEO + 원문 PDF 검증 ──────────────────────────────────
import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
COVERS = json.loads((FIXTURES / "imf_weo_covers.json").read_text(encoding="utf-8"))


def sdmx(code):
    return json.loads((FIXTURES / f"imf_weo_sdmx_{code}.json").read_text(encoding="utf-8"))


def test_weo_gives_the_edition_date_and_the_series():
    # 회차는 전망 지평이 아니라 데이터셋의 PUBLICATION_DATE 로 정한다.
    # 지평으로 정하면 지평을 안 늘리는 10월판이 4월판 날짜로 저장된다.
    published_at, series = imf.parse_weo(sdmx("NGDP_RPCH"))
    assert published_at == date(2026, 4, 14)
    assert round(series[2026], 1) == 1.9 and round(series[2027], 1) == 2.1


def test_weo_without_publication_date_fails():
    payload = sdmx("NGDP_RPCH")
    payload["data"]["dataSets"][0]["attributes"] = []
    with pytest.raises(ValueError, match="PUBLICATION_DATE"):
        imf.parse_weo(payload)


def test_regular_edition_label_comes_from_its_month():
    assert imf.regular_label(date(2026, 4, 14)) == "April 2026"
    assert imf.regular_label(date(2026, 10, 13)) == "October 2026"
    # WEO 데이터셋은 4·10월판만 싣는다 — 다른 달이면 가정이 깨진 것이다
    with pytest.raises(ValueError):
        imf.regular_label(date(2026, 7, 8))


def test_report_pdf_address_follows_the_media_path():
    assert imf.pdf_url("April 2026") == \
        "https://www.imf.org/-/media/Files/Publications/WEO/2026/April/English/text.ashx"
    assert imf.pdf_url("Update July 2026") == \
        "https://www.imf.org/-/media/Files/Publications/WEO/2026/Update/July/English/text.ashx"


@pytest.mark.parametrize("key,label", [
    ("2026-04", "April 2026"), ("2025-10", "October 2025"),
    ("2026-July-update", "Update July 2026"), ("2025-January-update", "Update January 2025"),
])
def test_cover_confirms_its_own_edition(key, label):
    imf.check_cover(COVERS[key], label)


@pytest.mark.parametrize("key,label", [
    ("2026-04", "October 2026"),          # 10월판 주소에 4월판이 걸려 있으면
    ("2026-July-update", "July 2026"),    # 업데이트를 정규 회차로 착각하면
    ("2026-04", "Update April 2026"),
])
def test_cover_of_another_edition_is_refused(key, label):
    with pytest.raises(ValueError):
        imf.check_cover(COVERS[key], label)


def test_collect_builds_records_from_weo_and_links_the_checked_pdf(monkeypatch):
    monkeypatch.setattr(imf, "fetch_weo", sdmx)
    fetched = []
    monkeypatch.setattr(imf, "report_cover", lambda url: fetched.append(url) or COVERS["2026-04"])
    records = imf.collect(date(2026, 9, 30))
    got = {(r.indicator, r.target_year): r.value for r in records}
    assert got == {("gdp_growth", 2026): 1.9, ("gdp_growth", 2027): 2.1,
                   ("cpi", 2026): 2.5, ("cpi", 2027): 1.9,
                   ("unemp_rate", 2026): 2.8, ("unemp_rate", 2027): 2.9}
    assert fetched == [imf.pdf_url("April 2026")]
    r = records[0]
    assert r.published_at == date(2026, 4, 14)
    assert r.report_title == "IMF World Economic Outlook, April 2026"
    assert r.source_url == imf.pdf_url("April 2026")
    assert r.landing_url == imf.report_url("April 2026", date(2026, 4, 14))


def test_collect_refuses_indicators_from_different_editions(monkeypatch):
    def mixed(code):
        payload = sdmx(code)
        if code == "LUR":
            attrs = payload["data"]["dataSets"][0]["attributes"]
            names = [a["id"] for a in payload["data"]["structures"][0]["attributes"]["dataSet"]]
            attrs[names.index("PUBLICATION_DATE")] = ["2025-10-14T13:00:00Z"]
        return payload
    monkeypatch.setattr(imf, "fetch_weo", mixed)
    monkeypatch.setattr(imf, "report_cover", lambda url: COVERS["2026-04"])
    with pytest.raises(ValueError, match="회차"):
        imf.collect(date(2026, 9, 30))


# ── 업데이트(1·7월): 기재부 보도참고 + 업데이트 PDF 부록표 1 ─────────────────

@pytest.mark.parametrize("name,published,want", [
    ("2026_july", date(2026, 7, 8), {2026: 2.6, 2027: 2.5}),
    ("2026_january", date(2026, 1, 19), {2026: 1.9, 2027: 2.1}),
    ("2025_july", date(2025, 7, 29), {2025: 0.8, 2026: 1.8}),
    ("2025_january", date(2025, 1, 17), {2025: 2.0, 2026: 2.1}),
])
def test_update_annex_gives_korea_growth(name, published, want):
    text = (FIXTURES / f"imf_update_{name}_annex.txt").read_text(encoding="utf-8")
    assert imf.update_growth(text, published.year) == want


def test_update_annex_without_korea_fails():
    text = (FIXTURES / "imf_update_2026_july_annex.txt").read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        imf.update_growth(text.replace("Korea", "Kore"), 2026)


def test_update_rounds_come_from_moef_notices():
    notices = [
        ("IMF", date(2026, 7, 8), "[보도참고] 2026년 국제통화기금(IMF) 7월 세계경제전망(WEO) 업데이트"),
        ("IMF", date(2026, 4, 14), "[보도참고] 국제통화기금(IMF), 4월 세계경제전망 발표"),
        # 2025년 보도참고는 제목에 '업데이트' 가 없다 — 달로 가른다
        ("IMF", date(2025, 7, 29), "[보도참고] 국제통화기금(IMF) 7월 세계경제전망 발표"),
        ("IMF", date(2025, 11, 24), "[보도참고] 국제통화기금(IMF) 2025년 한국 연례협의 보고서 발표"),
        ("OECD", date(2026, 7, 2), "[보도참고] 경제협력개발기구, 7월 경제전망 발표"),
    ]
    assert imf.update_rounds(notices) == [("Update July 2026", date(2026, 7, 8)),
                                          ("Update July 2025", date(2025, 7, 29))]


def test_collect_update_reads_the_latest_update(monkeypatch):
    annex = (FIXTURES / "imf_update_2026_july_annex.txt").read_text(encoding="utf-8")
    monkeypatch.setattr(imf, "report_pages", lambda url: [COVERS["2026-July-update"], annex])
    notices = lambda: [("IMF", date(2026, 7, 8), "[보도참고] 2026년 국제통화기금(IMF) 7월 세계경제전망(WEO) 업데이트")]
    records = imf.collect_update(date(2026, 9, 30), notices=notices)
    assert {(r.indicator, r.target_year): r.value for r in records} == \
        {("gdp_growth", 2026): 2.6, ("gdp_growth", 2027): 2.5}
    r = records[0]
    assert r.report_title == "IMF World Economic Outlook Update, July 2026"
    assert r.published_at == date(2026, 7, 8)
    assert r.source_url == imf.pdf_url("Update July 2026")
    assert r.landing_url.endswith("/2026/07/08/world-economic-outlook-update-july-2026")
