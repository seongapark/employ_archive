from datetime import date

from domains.forecast.pipeline import documents as d


def test_sources_covers_the_six_text_bearing_orgs():
    assert set(d.SOURCES) == {"bok", "kdi", "kli", "kiet", "keis", "oecd_interim"}


def test_imf_and_oecd_are_absent_because_they_have_no_document_text():
    assert "imf" not in d.SOURCES
    assert "oecd" not in d.SOURCES


def test_listed_carries_only_the_indicators_that_org_forecasts(monkeypatch):
    from domains.forecast.pipeline.collectors import kiet
    from domains.forecast.pipeline.report import Issue

    monkeypatch.setattr(kiet, "list_issues",
                        lambda: [Issue("2026년 전망", date(2026, 5, 26), "https://x/y")])
    listed = d.SOURCES["kiet"]()
    assert listed[0].indicators == ("gdp_growth",)
    assert listed[0].org == "KIET"


def test_fetch_pages_is_lazy_even_when_the_url_needs_a_detail_page(monkeypatch):
    # KIET 는 PDF 주소를 상세 페이지에서 읽는다. 목록 단계에서 그것을 받으면
    # 회차 30여 개마다 네트워크를 탄다 — 주소도 본문과 함께 지연돼야 한다.
    from domains.forecast.pipeline import http
    from domains.forecast.pipeline.collectors import kiet
    from domains.forecast.pipeline.report import Issue

    monkeypatch.setattr(kiet, "list_issues",
                        lambda: [Issue("t", date(2026, 5, 26), "https://x/y")])
    monkeypatch.setattr(http, "get", _boom)
    d.SOURCES["kiet"]()  # 여기서 터지면 안 된다


def test_fetch_pages_returns_the_source_url_with_the_pages(monkeypatch):
    from domains.forecast.pipeline import http, pdf
    from domains.forecast.pipeline.collectors import kli
    from domains.forecast.pipeline.report import Issue

    # kli._list_no 는 "list_no=" 뒤의 숫자를 읽는다(kli.VIEW_URL 참고) — 브리프
    # 원문의 "https://x/list?no=7" 은 이 낱말을 담지 않아 _list_no 가
    # AttributeError 로 터진다. 실제 회차 URL 모양대로 "list_no=" 를 넣는다.
    monkeypatch.setattr(kli, "list_issues",
                        lambda: [Issue("t", date(2026, 1, 2), "https://x/list_no=7")])
    monkeypatch.setattr(http, "get", lambda url, **k: _Resp(b"pdf"))
    monkeypatch.setattr(pdf, "page_texts", lambda data: ["1쪽", "2쪽"])
    url, pages = d.SOURCES["kli"]()[0].fetch_pages()
    assert url.startswith("http")
    assert pages == ["1쪽", "2쪽"]


class _Resp:
    def __init__(self, content):
        self.content = content


def _boom(*a, **k):
    raise AssertionError("목록 단계에서 네트워크를 탔다")
