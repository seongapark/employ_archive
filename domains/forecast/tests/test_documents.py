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


def test_bok_fetch_pages_resolves_the_pdf_link_from_the_detail_page(monkeypatch):
    from domains.forecast.pipeline import http, pdf
    from domains.forecast.pipeline.collectors import bok
    from domains.forecast.pipeline.report import Issue

    issue = Issue("경제전망보고서(2026년 8월)", date(2026, 8, 27), "https://x/issue")
    pdf_url = "https://www.bok.or.kr/fileSrc/report.pdf"
    monkeypatch.setattr(bok, "list_issues", lambda: [issue])

    def fake_get(url, **k):
        if url == issue.url:
            return _TextResp('<a href="/fileSrc/report.pdf">다운로드</a>')
        assert url == pdf_url, f"예상 밖 주소: {url}"
        return _Resp(b"pdf-bytes")

    monkeypatch.setattr(http, "get", fake_get)
    monkeypatch.setattr(pdf, "page_texts", lambda data: ["1쪽"])

    url, pages = d.SOURCES["bok"]()[0].fetch_pages()
    assert url == pdf_url
    assert pages == ["1쪽"]


def test_oecd_interim_fetch_pages_uses_the_editions_url(monkeypatch):
    from domains.forecast.pipeline import http, pdf
    from domains.forecast.pipeline.collectors import oecd_interim

    monkeypatch.setattr(oecd_interim, "EDITIONS",
                        {"March 2026": (date(2026, 3, 26), "https://x/oecd.pdf")})
    monkeypatch.setattr(http, "get", lambda url, **k: _Resp(b"pdf"))
    monkeypatch.setattr(pdf, "page_texts", lambda data: ["1쪽"])

    listed = d.SOURCES["oecd_interim"]()
    assert listed[0].published_at == date(2026, 3, 26)
    url, pages = listed[0].fetch_pages()
    assert url == "https://x/oecd.pdf"
    assert pages == ["1쪽"]


def test_keis_fetch_pages_ocrs_the_full_document_at_400dpi(monkeypatch):
    """KEIS 는 텍스트 레이어가 없어 전문을 OCR 한다. 이 dpi=400·preprocess=True·
    pages=None(전 쪽) 은 설계 결정이지 구현 세부가 아니다 — 누군가 KEIS 자체의
    2단계(저해상도 스크리닝 → 후보만 정밀 판독) 방식으로 "최적화"하면 LLM이
    읽는 범위가 조용히 좁아져 이 기능 전환의 취지 자체가 무너진다."""
    from domains.forecast.pipeline import http, ocr
    from domains.forecast.pipeline.collectors import keis
    from domains.forecast.pipeline.report import Issue

    issue = Issue("2026년 제5호", date(2026, 6, 1), "https://x/detail")
    listed_issue = keis.ListedIssue(issue=issue, pdf_url="https://x/pdf")
    monkeypatch.setattr(keis, "list_issues", lambda: [listed_issue])
    monkeypatch.setattr(http, "get", lambda url, **k: _Resp(b"pdf-bytes"))

    captured = {}

    def fake_page_texts(data, pages, *, dpi, preprocess):
        captured.update(data=data, pages=pages, dpi=dpi, preprocess=preprocess)
        return ["1쪽", "2쪽"]

    monkeypatch.setattr(ocr, "page_texts", fake_page_texts)

    url, pages = d.SOURCES["keis"]()[0].fetch_pages()
    assert url == "https://x/pdf"
    assert pages == ["1쪽", "2쪽"]
    assert captured["data"] == b"pdf-bytes"
    assert captured["pages"] is None
    assert captured["dpi"] == 400
    assert captured["preprocess"] is True


def test_kdi_fetch_pages_unfolds_the_february_header(monkeypatch):
    """KDI 2월호는 수정폭 헤더가 세로로 접혀 나온다. _unfold_february_header 를
    빠뜨리면 그 회차 본문이 어긋난다 — 호출 여부가 아니라 실제로 펴진 결과가
    돌아오는지를 확인한다(호출만 확인하면 인자 순서가 바뀌어도 통과해 버린다).
    """
    from domains.forecast.pipeline import http, pdf
    from domains.forecast.pipeline.collectors import kdi
    from domains.forecast.pipeline.report import Issue

    issue = Issue("경제전망(2026년 2월)", date(2026, 2, 1), "https://x/issue")
    chapter_url = "https://x/chapter.pdf"
    # 연도 한 줄 → 연도 두 개 줄 → 수정폭 줄 → 기간 줄, 접힌 모양 그대로.
    folded = "\n".join(["2026", "2025 2026", "수정폭1)", "상반기 하반기 연간 연간"])
    unfolded = "\n".join(["2025 2026 2026", "상반기 하반기 연간 수정폭1)"])
    assert kdi._unfold_february_header(folded) == unfolded  # 전제 확인

    monkeypatch.setattr(kdi, "list_issues", lambda: [issue])
    monkeypatch.setattr(kdi, "parse_chapters",
                        lambda html: [("요약", chapter_url)])

    def fake_get(url, **k):
        if url == issue.url:
            return _TextResp("<html>본문</html>")
        assert url == chapter_url, f"예상 밖 주소: {url}"
        return _Resp(b"pdf-bytes")

    monkeypatch.setattr(http, "get", fake_get)
    monkeypatch.setattr(pdf, "page_texts", lambda data: [folded])
    # find_summary_table 자체의 판정 로직은 kdi 자신의 테스트가 이미 지킨다.
    # 여기서는 documents.py 가 unfold 된 페이지를 넘기고 그대로 돌려주는지만 본다.
    monkeypatch.setattr(pdf, "find_summary_table",
                        lambda pages, labels, required: (1, pages[0]))

    url, pages = d.SOURCES["kdi"]()[0].fetch_pages()
    assert url == chapter_url
    assert pages == [unfolded]


class _Resp:
    def __init__(self, content):
        self.content = content


class _TextResp:
    def __init__(self, text):
        self.text = text


def _boom(*a, **k):
    raise AssertionError("목록 단계에서 네트워크를 탔다")
