from datetime import date

from domains.forecast.pipeline import documents as d


def test_sources_covers_the_text_bearing_orgs():
    # MOEF 는 2026-09-10 에 붙였다 — 수집기가 생기면서 근거 대상이 됐다.
    assert set(d.SOURCES) == {"bok", "kdi", "kli", "kiet", "keis", "oecd_interim",
                              "moef"}


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
    monkeypatch.setattr(pdf, "page_texts_with_breaks", lambda data: ["1쪽", "2쪽"])
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
    monkeypatch.setattr(pdf, "page_texts_with_breaks", lambda data: ["1쪽"])

    url, pages = d.SOURCES["bok"]()[0].fetch_pages()
    assert url == pdf_url
    assert pages == ["1쪽"]


def test_oecd_interim_fetch_pages_uses_the_editions_url(monkeypatch):
    from domains.forecast.pipeline import http, pdf
    from domains.forecast.pipeline.collectors import oecd_interim

    monkeypatch.setattr(oecd_interim, "EDITIONS",
                        {"March 2026": (date(2026, 3, 26), "https://x/oecd.pdf")})
    monkeypatch.setattr(http, "get", lambda url, **k: _Resp(b"pdf"))
    monkeypatch.setattr(pdf, "page_texts_with_breaks", lambda data: ["1쪽"])

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


class _Resp:
    def __init__(self, content):
        self.content = content


class _TextResp:
    def __init__(self, text):
        self.text = text


def _boom(*a, **k):
    raise AssertionError("목록 단계에서 네트워크를 탔다")


def test_pdf_paths_read_the_text_with_paragraph_breaks(monkeypatch):
    """근거 경로는 문단 나눔이 들어간 원문을 쓴다 — llm_verify 가 표지도
    마침표도 없는 항목의 시작을 그 빈 줄로 알아본다. 매일 도는 수집기가
    쓰는 pdf.page_texts 는 그대로 둔다."""
    from domains.forecast.pipeline import http, pdf
    from domains.forecast.pipeline.collectors import kli
    from domains.forecast.pipeline.report import Issue

    monkeypatch.setattr(kli, "list_issues",
                        lambda: [Issue("t", date(2026, 1, 2), "https://x/list_no=7")])
    monkeypatch.setattr(http, "get", lambda url, **k: _Resp(b"pdf"))
    monkeypatch.setattr(pdf, "page_texts", _boom)
    monkeypatch.setattr(pdf, "page_texts_with_breaks",
                        lambda data: ["항목 하나\n\n항목 둘"])

    _, pages = d.SOURCES["kli"]()[0].fetch_pages()

    assert pages == ["항목 하나\n\n항목 둘"]


def test_kdi_chapter_search_uses_the_unbroken_text_so_the_february_header_unfolds(monkeypatch):
    """_unfold_february_header 는 네 줄이 잇달아 있을 때만 손댄다. 문단 나눔이
    그 사이에 빈 줄을 넣으면 모양이 안 맞아 조용히 안 펴지고, 그 회차는
    요약표를 실은 장을 못 찾는다. 그래서 장 선택은 빈 줄이 없는 원문으로
    하고, 빈 줄이 든 원문은 LLM 에게만 넘긴다.

    호출 여부가 아니라 find_summary_table 이 실제로 받은 원문을 본다 —
    호출만 확인하면 인자 순서가 바뀌어도 통과해 버린다."""
    from domains.forecast.pipeline import http, pdf
    from domains.forecast.pipeline.collectors import kdi
    from domains.forecast.pipeline.report import Issue

    issue = Issue("경제전망(2026년 2월)", date(2026, 2, 1), "https://x/issue")
    chapter_url = "https://x/chapter.pdf"
    folded = "\n".join(["2026", "2025 2026", "수정폭1)", "상반기 하반기 연간 연간"])
    unfolded = "\n".join(["2025 2026 2026", "상반기 하반기 연간 수정폭1)"])
    broken = "\n".join(["2026", "", "2025 2026", "수정폭1)", "상반기 하반기 연간 연간"])
    assert kdi._unfold_february_header(broken) == broken  # 전제: 빈 줄이 끼면 안 펴진다

    monkeypatch.setattr(kdi, "list_issues", lambda: [issue])
    monkeypatch.setattr(kdi, "parse_chapters", lambda html: [("요약", chapter_url)])

    def fake_get(url, **k):
        if url == issue.url:
            return _TextResp("<html>본문</html>")
        return _Resp(b"pdf-bytes")

    monkeypatch.setattr(http, "get", fake_get)
    monkeypatch.setattr(pdf, "page_texts", lambda data: [folded])
    monkeypatch.setattr(pdf, "page_texts_with_breaks", lambda data: [broken])

    seen = {}

    def fake_find(pages, labels, required):
        seen["pages"] = pages
        return (1, pages[0])

    monkeypatch.setattr(pdf, "find_summary_table", fake_find)

    url, pages = d.SOURCES["kdi"]()[0].fetch_pages()

    assert seen["pages"] == [unfolded]   # 장 선택은 펴진 원문으로
    assert pages == [broken]             # LLM 에는 문단 나눔이 든 원문으로


def test_bok_만_쪽을_좁힌다():
    # 좁힘은 조용한 미수확을 부른다 — 꼭 좁혀야 하는 곳에만 준다.
    # BOK 은 큰 회차가 프롬프트 276k 토큰이라 분당 한도(200k)에 안 들어간다.
    assert d.BOK_MAX_PAGES == 40


def test_쪽_제한이_없으면_전문을_그대로_준다(monkeypatch):
    from domains.forecast.pipeline import pdf, http
    monkeypatch.setattr(http, "get", lambda url, **kw: type("R", (), {"text": "", "content": b""})())
    monkeypatch.setattr(pdf, "page_texts_with_breaks", lambda data: [f"{i}쪽" for i in range(60)])
    full = d._via_detail("u", lambda html: "pdf")()
    capped = d._via_detail("u", lambda html: "pdf", max_pages=40)()
    assert len(full[1]) == 60
    assert len(capped[1]) == 40
    assert capped[1][-1] == "39쪽"
