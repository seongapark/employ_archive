from datetime import date
from pathlib import Path

from domains.forecast.pipeline.collectors import kdi

FIXTURES = Path(__file__).parent / "fixtures"
PAGE = (FIXTURES / "kdi_economy.html").read_text(encoding="utf-8")
TABLE = (FIXTURES / "kdi_2026-08_summary.txt").read_text(encoding="utf-8")
FIRST_HALF_TABLE = (FIXTURES / "kdi_2026-05_summary.txt").read_text(encoding="utf-8")

ISSUE = kdi.Issue(
    title="KDI 경제전망 | 수정, 2026년 8월",
    published_at=date(2026, 8, 19),
    url="https://www.kdi.re.kr/research/economy",
)
PDF_URL = "https://www.kdi.re.kr/file/download?atch_no=x"


def by_key(records):
    """연간 레코드만 (지표, 연도) 로 뽑는다 — 반기는 별도 테스트에서 본다."""
    return {(r.indicator, r.target_year): r
            for r in records if r.target_period == "annual"}


def test_parse_issue_reads_title_and_publication_date():
    issue = kdi.parse_issue(PAGE, "https://www.kdi.re.kr/research/economy")
    assert issue.title == "KDI 경제전망 | 수정, 2026년 8월"
    assert issue.published_at == date(2026, 8, 19)
    assert issue.url == "https://www.kdi.re.kr/research/economy"


def test_parse_chapters_returns_labels_with_absolute_urls():
    chapters = kdi.parse_chapters(PAGE)
    assert chapters[0][0] == "요약"
    assert chapters[0][1].startswith("https://www.kdi.re.kr/file/download?atch_no=")
    assert [label for label, _ in chapters] == [
        "요약", "현 경제상황에 대한 인식", "2026~27년 국내경제 전망",
    ]


def test_parse_reads_annual_values_of_the_revision_issue():
    got = by_key(kdi.parse(TABLE, ISSUE, PDF_URL, source_page=20))
    assert got[("emp_change", 2026)].value == 11.0
    assert got[("emp_change", 2027)].value == 20.0
    assert got[("gdp_growth", 2026)].value == 3.2
    assert got[("cpi", 2026)].value == 2.7
    assert got[("unemp_rate", 2027)].value == 2.8


def test_parse_omits_indicators_absent_from_the_kdi_table():
    records = kdi.parse(TABLE, ISSUE, PDF_URL, source_page=20)
    assert "emp_rate" not in {r.indicator for r in records}  # KDI 표에는 고용률이 없다


def test_parse_covers_forecast_years_only():
    records = kdi.parse(TABLE, ISSUE, PDF_URL, source_page=20)
    assert {r.target_year for r in records} == {2026, 2027}


def test_parse_keeps_half_year_forecasts_where_the_table_has_them():
    records = {(r.indicator, r.target_year, r.target_period): r
               for r in kdi.parse(TABLE, ISSUE, PDF_URL, source_page=20)}
    assert records[("emp_change", 2026, "h1")].value == 11.0
    assert records[("emp_change", 2026, "h2")].value == 12.0
    assert records[("emp_change", 2026, "h1")].id == "kdi-2026-08-emp_change-2026-h1"
    # 수정호 표는 2027년을 연간만 싣는다 — 없는 반기를 지어내면 안 된다
    assert ("emp_change", 2027, "h1") not in records


def test_parse_record_fields():
    r = by_key(kdi.parse(TABLE, ISSUE, PDF_URL, source_page=20))[("emp_change", 2026)]
    assert r.id == "kdi-2026-08-emp_change-2026"
    assert r.org == "KDI"
    assert r.org_name_ko == "KDI"
    assert r.report_title == "KDI 경제전망 | 수정, 2026년 8월"
    assert r.published_at == date(2026, 8, 19)
    assert r.unit == "만명"
    assert r.confidence == "extracted"
    assert r.source_url == PDF_URL
    assert r.source_page == 20
    assert r.landing_url == ISSUE.url


def test_parse_handles_the_first_half_issue_layout():
    issue = kdi.Issue(
        title="KDI 경제전망, 2026 상반기",
        published_at=date(2026, 5, 14),
        url="https://www.kdi.re.kr/research/economy?pub_no=19180",
    )
    got = by_key(kdi.parse(FIRST_HALF_TABLE, issue, PDF_URL, source_page=10))
    assert got[("emp_change", 2026)].value == 17.0
    assert got[("gdp_growth", 2027)].value == 1.7
    assert got[("emp_change", 2026)].id == "kdi-2026-05-emp_change-2026"
    assert {r.target_year for r in got.values()} == {2026, 2027}  # 2024·2025는 실적


def test_parse_issue_ignores_earlier_headings_on_the_page():
    # 실제 페이지에는 회차 제목 앞에 네비게이션용 <h2>가 여러 개 있다.
    # 정규식이 그 사이를 건너뛰면 제목에 메뉴 전체가 딸려 들어온다.
    decoy = '<h2><b>연구</b><p>KDI는 "미래를 여는 연구"를 통해 정책 대안을 제시합니다.</p></h2>'
    issue = kdi.parse_issue(decoy + PAGE, "https://www.kdi.re.kr/research/economy")
    assert issue.title == "KDI 경제전망 | 수정, 2026년 8월"
