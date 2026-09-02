from datetime import date
from pathlib import Path

from domains.forecast.pipeline.collectors import bok

FIXTURES = Path(__file__).parent / "fixtures"
RSS = (FIXTURES / "bok_rss.xml").read_text(encoding="utf-8")
VIEW = (FIXTURES / "bok_view.html").read_text(encoding="utf-8")
TABLE = (FIXTURES / "bok_2026-08_summary.txt").read_text(encoding="utf-8")
MAY_TABLE = (FIXTURES / "bok_2026-05_summary.txt").read_text(encoding="utf-8")

ISSUE = bok.Issue(
    title="경제전망보고서(2026년 8월)",
    published_at=date(2026, 8, 27),
    url="https://www.bok.or.kr/portal/bbs/P0002359/view.do?nttId=11064210&menuNo=200066",
)
PDF_URL = "https://www.bok.or.kr/fileSrc/portal/x/1/y.pdf"


def by_key(records):
    """연간 레코드만 (지표, 연도) 로 뽑는다 — 반기는 별도 테스트에서 본다."""
    return {(r.indicator, r.target_year): r
            for r in records if r.target_period == "annual"}


def test_parse_rss_returns_issues_newest_first():
    issues = bok.parse_rss(RSS)
    assert issues[0].title == "경제전망보고서(2026년 8월)"
    assert issues[0].published_at == date(2026, 8, 27)
    assert issues[0].url.endswith("nttId=11064210&menuNo=200066")
    assert issues[1].published_at == date(2026, 5, 28)


def test_parse_rss_skips_notices_that_are_not_a_forecast_round():
    notice = (
        "<item><title>&lt;안내&gt; 경제전망 발표시점 변경</title>"
        "<pubDate>Thu, 31 Oct 2019 09:23:54 +0900</pubDate>"
        "<link><![CDATA[https://www.bok.or.kr/portal/bbs/P0002359/view.do?nttId=1]]></link>"
        "</item>"
    )
    issues = bok.parse_rss(RSS.replace("<item>", notice + "<item>", 1))
    assert all("안내" not in issue.title for issue in issues)
    assert issues[0].title == "경제전망보고서(2026년 8월)"


def test_parse_pdf_link_returns_absolute_url():
    assert bok.parse_pdf_link(VIEW) == (
        "https://www.bok.or.kr/fileSrc/portal/"
        "dfe965a8e38a4e4b9fd1a6989a7ee18e/1/920b4555aa3f47c7a73908ebe7576644.pdf"
    )


def test_parse_reads_annual_values_of_the_summary_table():
    got = by_key(bok.parse(TABLE, ISSUE, PDF_URL, source_page=16))
    assert got[("emp_change", 2026)].value == 14.0
    assert got[("emp_change", 2027)].value == 20.0
    assert got[("emp_rate", 2026)].value == 62.9
    assert got[("unemp_rate", 2026)].value == 2.9
    assert got[("gdp_growth", 2026)].value == 3.3
    assert got[("cpi", 2027)].value == 2.3


def test_parse_covers_forecast_years_only():
    records = bok.parse(TABLE, ISSUE, PDF_URL, source_page=16)
    assert {r.target_year for r in records} == {2026, 2027}  # 2025는 실적이라 제외


def test_parse_keeps_half_year_forecasts_alongside_the_annual_one():
    records = {(r.indicator, r.target_year, r.target_period): r
               for r in bok.parse(TABLE, ISSUE, PDF_URL, source_page=16)}
    assert records[("emp_change", 2026, "h1")].value == 11.0
    assert records[("emp_change", 2026, "h2")].value == 18.0
    assert records[("gdp_growth", 2027, "h1")].value == 2.5
    assert records[("emp_change", 2026, "h1")].id == "bok-2026-08-emp_change-2026-h1"


def test_parse_record_fields():
    r = by_key(bok.parse(TABLE, ISSUE, PDF_URL, source_page=16))[("emp_change", 2026)]
    assert r.id == "bok-2026-08-emp_change-2026"
    assert r.org == "BOK"
    assert r.org_name_ko == "한국은행"
    assert r.report_title == "경제전망보고서(2026년 8월)"
    assert r.published_at == date(2026, 8, 27)
    assert r.unit == "만명"
    assert r.confidence == "extracted"
    assert r.source_url == PDF_URL
    assert r.source_page == 16
    assert r.landing_url == ISSUE.url


def test_parse_handles_the_may_issue_layout():
    may_issue = ISSUE._replace(
        title="경제전망보고서(2026년 5월)", published_at=date(2026, 5, 28)
    )
    got = by_key(bok.parse(MAY_TABLE, may_issue, PDF_URL, source_page=16))
    assert got[("emp_change", 2026)].value == 18.0
    assert got[("emp_rate", 2027)].value == 63.1
    assert got[("emp_change", 2026)].id == "bok-2026-05-emp_change-2026"



class _Resp:
    def __init__(self, text="", content=b""):
        self.text = text
        self.content = content


def test_list_issues_returns_rounds_newest_first(monkeypatch):
    monkeypatch.setattr(bok.http, "get", lambda url, **kw: _Resp(text=RSS))
    issues = bok.list_issues()
    assert [i.published_at for i in issues] == sorted(
        [i.published_at for i in issues], reverse=True)
    assert issues[0].title.startswith("경제전망보고서")


def test_collect_issue_reads_one_named_round(monkeypatch):
    issue = bok.Issue("경제전망보고서(2026년 8월)", date(2026, 8, 27), "https://x/view")

    def fake_get(url, **kw):
        if url == issue.url:
            return _Resp(text='<a href="/fileSrc/x.pdf">첨부</a>')
        assert url == "https://www.bok.or.kr/fileSrc/x.pdf"
        return _Resp(content=b"%PDF")

    monkeypatch.setattr(bok.http, "get", fake_get)
    monkeypatch.setattr(bok.pdf, "page_texts", lambda data: ["표지", TABLE])

    records = bok.collect_issue(issue)
    got = {(r.indicator, r.target_year, r.target_period): r for r in records}
    assert got[("emp_change", 2026, "annual")].value == 14.0
    assert got[("emp_change", 2026, "annual")].source_page == 2
    assert got[("emp_change", 2026, "annual")].published_at == date(2026, 8, 27)


def test_collect_uses_the_newest_round(monkeypatch):
    seen = []

    monkeypatch.setattr(bok, "list_issues", lambda: [
        bok.Issue("경제전망보고서(2026년 8월)", date(2026, 8, 27), "u-new"),
        bok.Issue("경제전망보고서(2026년 5월)", date(2026, 5, 28), "u-old"),
    ])
    monkeypatch.setattr(bok, "collect_issue", lambda issue: seen.append(issue) or [])

    bok.collect(date(2026, 8, 30))
    assert [i.url for i in seen] == ["u-new"]
