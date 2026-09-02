from datetime import date
from pathlib import Path

import pytest

from domains.forecast.pipeline.collectors import kdi

FIXTURES = Path(__file__).parent / "fixtures"
PAGE = (FIXTURES / "kdi_economy.html").read_text(encoding="utf-8")
TABLE = (FIXTURES / "kdi_2026-08_summary.txt").read_text(encoding="utf-8")
FIRST_HALF_TABLE = (FIXTURES / "kdi_2026-05_summary.txt").read_text(encoding="utf-8")
FEBRUARY_2025_TABLE = (FIXTURES / "kdi_2025-02_summary.txt").read_text(encoding="utf-8")
FEBRUARY_2026_TABLE = (FIXTURES / "kdi_2026-02_summary.txt").read_text(encoding="utf-8")

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


def test_unfold_february_header_leaves_flat_headers_byte_identical():
    # 8월호·5월호는 이미 8월호 모양(연도·기간이 한 줄씩)이라 접힌 부분이 없다 —
    # _unfold_february_header 이 손대지 않고 그대로 돌려줘야 한다.
    assert kdi._unfold_february_header(TABLE) == TABLE
    assert kdi._unfold_february_header(FIRST_HALF_TABLE) == FIRST_HALF_TABLE


def test_parse_handles_the_february_issue_layout_2025():
    # kdi_2025-02_summary.txt (실제 pdfplumber 페이지 텍스트) 6번째 줄:
    #   "국내총생산 2.8 1.3 2.0 0.9 2.2 1.6 -0.4"
    # 열 순서는 [2024 상반기·하반기·연간][2025 상반기·하반기·연간][2025 수정폭].
    # 발표일이 2025년이므로 2024(실적)는 report.records_from_values 가 걸러내고
    # 2025 상반기=0.9, 하반기=2.2, 연간=1.6 만 남는다 — 숫자는 그 줄에서 그대로 옮겼다.
    issue = kdi.Issue(
        title="KDI 경제전망, 2025년 2월",
        published_at=date(2025, 2, 12),
        url="https://www.kdi.re.kr/research/economy?pub_no=1",
    )
    records = {(r.indicator, r.target_year, r.target_period): r
               for r in kdi.parse(FEBRUARY_2025_TABLE, issue, PDF_URL, source_page=4)}
    assert {r.target_year for r in records.values()} == {2025}  # 2024는 실적이라 빠진다
    assert records[("gdp_growth", 2025, "h1")].value == 0.9
    assert records[("gdp_growth", 2025, "h2")].value == 2.2
    assert records[("gdp_growth", 2025, "annual")].value == 1.6
    # 취업자 수(증감) 줄: "취업자 수(증감) 22 10 16 9 11 10 -4"
    assert records[("emp_change", 2025, "annual")].value == 10.0
    # 소비자물가 줄: "소비자물가 2.8 1.8 2.3 1.8 1.5 1.6 0.0"
    assert records[("cpi", 2025, "annual")].value == 1.6
    # 실업률 줄: "실업률 3.1 2.5 2.8 3.2 2.6 2.9 0.1"
    assert records[("unemp_rate", 2025, "annual")].value == 2.9


def test_parse_handles_the_february_issue_layout_2026():
    # kdi_2026-02_summary.txt 7번째 줄:
    #   "국내총생산 0.3 1.6 1.0 2.2 1.6 1.9 0.1"
    # 열 순서는 위와 같되 연도가 [2025][2026][2026 수정폭] 이다. 발표일이
    # 2026년이므로 2025(실적)는 걸러지고 2026 상반기=2.2, 하반기=1.6, 연간=1.9 만 남는다.
    issue = kdi.Issue(
        title="KDI 경제전망, 2026년 2월",
        published_at=date(2026, 2, 12),
        url="https://www.kdi.re.kr/research/economy?pub_no=2",
    )
    records = {(r.indicator, r.target_year, r.target_period): r
               for r in kdi.parse(FEBRUARY_2026_TABLE, issue, PDF_URL, source_page=5)}
    assert {r.target_year for r in records.values()} == {2026}  # 2025는 실적이라 빠진다
    assert records[("gdp_growth", 2026, "h1")].value == 2.2
    assert records[("gdp_growth", 2026, "h2")].value == 1.6
    assert records[("gdp_growth", 2026, "annual")].value == 1.9
    # 취업자 수(증감) 줄: "취업자 수(증감) 18 21 19 19 16 17 2"
    assert records[("emp_change", 2026, "annual")].value == 17.0
    # 소비자물가 줄: "소비자물가 2.1 2.2 2.1 2.1 2.1 2.1 0.1"
    assert records[("cpi", 2026, "annual")].value == 2.1
    # 실업률 줄: "실업률 3.1 2.6 2.8 3.1 2.5 2.8 0.0"
    assert records[("unemp_rate", 2026, "annual")].value == 2.8


def test_unfold_february_header_leaves_a_drifted_shape_alone_to_fail_loudly():
    # 연도 두 개짜리 줄("2024p 2025")이 없으면 네 줄 모양이 아니므로 손대지
    # 않는다. 그러면 헤더에 연도가 "2025" 하나뿐인 채로 원래 pdf.parse_summary_table
    # 이 돌게 되는데, 이번엔 기간 블록이 4개([수정폭][상반기·하반기·연간]x2)로
    # 잡혀 연도 1개와 어긋나 시끄럽게 실패한다 — 이 모양이 또 바뀌면 조용히
    # 넘어가지 않고 바로 드러난다는 뜻이다.
    #
    # (수정폭 표시 줄만 지우는 변형도 시험해 봤지만, 그 경우엔 우연히 기간
    # 블록 수가 연도 수와 맞아떨어져 조용히 잘못된 값을 만든다 — pdf.py 의
    # 기존 동작이고 이 픽스는 그 경로를 손대지 않으므로 여기선 다루지 않는다.)
    lines = FEBRUARY_2025_TABLE.split("\n")
    year_block_index = lines.index("2024p 2025")
    missing_year_line = "\n".join(lines[:year_block_index] + lines[year_block_index + 1:])

    assert kdi._unfold_february_header(missing_year_line) == missing_year_line

    issue = kdi.Issue(
        title="KDI 경제전망, 2025년 2월",
        published_at=date(2025, 2, 12),
        url="https://www.kdi.re.kr/research/economy?pub_no=1",
    )
    with pytest.raises(ValueError):
        kdi.parse(missing_year_line, issue, PDF_URL, source_page=4)


# 실제 select 태그의 축약 발췌 — 1982년까지 이어지는 실제 범위를 흉내 낸다.
# "특별호"는 라벨에 연도가 없는 경우를 시험하기 위한 가상의 항목이다.
ISSUE_SELECT_HTML = """
<select id="yearSelectUpDown" name="date" onchange="dateChg(this.value);">
    <option value="19259" selected>2026년 8월</option>
    <option value="19180" >2026 상반기</option>
    <option value="18859" >2025년 8월</option>
    <option value="18476" >2024 하반기</option>
    <option value="18120" >2023 하반기</option>
    <option value="99999" >특별호</option>
    <option value="2990" >1982年 4/4</option>
    <option value="2989" >1982年 3/4</option>
    <option value="2988" >1982年 2/4</option>
</select>
"""


def test_parse_issue_list_returns_pub_nos_and_labels_newest_first():
    got = kdi.parse_issue_list(ISSUE_SELECT_HTML)
    assert got[0] == ("19259", "2026년 8월")
    assert got[-1] == ("2988", "1982年 2/4")
    assert [no for no, _ in got] == [
        "19259", "19180", "18859", "18476", "18120", "99999", "2990", "2989", "2988",
    ]


def test_parse_issue_list_raises_when_the_dropdown_is_missing():
    # 드롭다운이 없으면 빈 리스트가 아니라 예외다 — 안 그러면 백필이
    # 회차가 하나도 없는 것으로 착각하고 조용히 넘어간다
    with pytest.raises(ValueError):
        kdi.parse_issue_list("<html><body>본문만 있고 드롭다운은 없다</body></html>")


def test_parse_issue_ignores_earlier_headings_on_the_page():
    # 실제 페이지에는 회차 제목 앞에 네비게이션용 <h2>가 여러 개 있다.
    # 정규식이 그 사이를 건너뛰면 제목에 메뉴 전체가 딸려 들어온다.
    decoy = '<h2><b>연구</b><p>KDI는 "미래를 여는 연구"를 통해 정책 대안을 제시합니다.</p></h2>'
    issue = kdi.parse_issue(decoy + PAGE, "https://www.kdi.re.kr/research/economy")
    assert issue.title == "KDI 경제전망 | 수정, 2026년 8월"


class _Resp:
    def __init__(self, text="", content=b""):
        self.text = text
        self.content = content


def test_list_issues_reads_the_real_date_from_each_issue_page(monkeypatch):
    # 드롭다운은 pub_no 와 표시 라벨만 준다 — 실제 제목·발표일은 각 회차의
    # 본문을 열어야 나온다(kli.list_issues() 와 같은 순서).
    list_html = """
    <select id="yearSelectUpDown" name="date" onchange="dateChg(this.value);">
        <option value="19259" selected>2026년 8월</option>
        <option value="19180" >2026 상반기</option>
        <option value="18476" >2024 하반기</option>
    </select>
    """
    pages = {
        "19259": PAGE,  # 최신호는 기존 픽스처를 그대로 쓴다
        "19180": '<h2>KDI 경제전망, 2026 상반기 <p>2026.05.13</p></h2>',
        "18476": '<h2>KDI 경제전망, 2024 하반기 <p>2024.11.12</p></h2>',
    }

    def fake_get(url, **kwargs):
        if url == kdi.LIST_URL:
            return _Resp(text=list_html)
        no = url.rsplit("=", 1)[-1]
        return _Resp(text=pages[no])

    monkeypatch.setattr(kdi.http, "get", fake_get)

    issues = kdi.list_issues()
    assert [i.published_at for i in issues] == [
        date(2026, 8, 19), date(2026, 5, 13), date(2024, 11, 12),
    ]
    assert issues[0].url == kdi.ISSUE_URL.format(no="19259")


def test_list_issues_skips_pages_older_than_the_cutoff_without_fetching_them(monkeypatch):
    # 드롭다운은 1982년까지 이어진다. 라벨에서 커트라인보다 뚜렷하게 이전인
    # 연도가 읽히면 그 회차의 본문은 아예 열지 않는다(네트워크 요청 자체가
    # 없어야 한다). 라벨에 연도가 없는 항목은 걸러내지 않고 그냥 연다.
    fetched = []

    def fake_get(url, **kwargs):
        if url == kdi.LIST_URL:
            return _Resp(text=ISSUE_SELECT_HTML)
        fetched.append(url)
        return _Resp(text='<h2>더미 <p>2000.01.01</p></h2>')

    monkeypatch.setattr(kdi.http, "get", fake_get)

    kdi.list_issues(since_year=2024)

    fetched_nos = {u.rsplit("=", 1)[-1] for u in fetched}
    # 커트라인 이전(2023년, 1982년) 회차는 열어보지도 않는다
    assert fetched_nos.isdisjoint({"18120", "2990", "2989", "2988"})
    # 커트라인 그 해(2024)를 포함해 최신 회차는 연다
    assert {"19259", "19180", "18859", "18476"} <= fetched_nos
    # 라벨에 연도가 없으면 걸러내지 않고 그냥 연다
    assert "99999" in fetched_nos


def test_collect_fetches_the_listing_page_exactly_once(monkeypatch):
    # collect() 는 list_issues() 를 타지 않는다 — /research/economy 자체가
    # 최신 회차 본문이므로 그 페이지 하나만 보면 된다. 드롭다운 전체를
    # 훑는 list_issues() 를 불렀다면 이 테스트가 실패한다. collect_issue() 에
    # 이미 받아 둔 본문을 넘겨 같은 URL을 두 번 받지 않는지도 함께 본다.
    def boom():
        raise AssertionError("collect() 가 list_issues() 를 불렀다 — 드롭다운을 탈 필요가 없다")

    monkeypatch.setattr(kdi, "list_issues", boom)

    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        if url == kdi.LIST_URL:
            return _Resp(text=PAGE)
        return _Resp(content=b"%PDF")

    monkeypatch.setattr(kdi.http, "get", fake_get)
    monkeypatch.setattr(kdi.pdf, "page_texts", lambda data: [TABLE])

    records = kdi.collect(date(2026, 8, 30))
    assert records
    assert calls.count(kdi.LIST_URL) == 1


def test_collect_skips_a_chapter_whose_download_fails(monkeypatch):
    # 장은 본문 순서대로 시도한다. 앞 장 내려받기가 502로 죽으면 표가 실린
    # 뒷 장은 시도조차 못 하고 수집기 전체가 실패한다.
    chapters = kdi.parse_chapters(PAGE)
    failing = chapters[0][1]

    def fake_get(url, **kwargs):
        if url == kdi.LIST_URL:
            return _Resp(text=PAGE)
        if url == failing:
            raise ConnectionError("HTTP Error 502: Bad Gateway")
        return _Resp(content=b"%PDF")

    monkeypatch.setattr(kdi.http, "get", fake_get)
    monkeypatch.setattr(kdi.pdf, "page_texts", lambda data: [TABLE])

    records = kdi.collect(date(2026, 8, 30))
    assert records
    assert records[0].source_url == chapters[1][1]


def test_collect_raises_when_every_chapter_fails(monkeypatch):
    def fake_get(url, **kwargs):
        if url == kdi.LIST_URL:
            return _Resp(text=PAGE)
        raise ConnectionError("HTTP Error 502: Bad Gateway")

    monkeypatch.setattr(kdi.http, "get", fake_get)

    with pytest.raises(ValueError):
        kdi.collect(date(2026, 8, 30))


def test_pick_would_blend_indicators_on_the_real_headline_summary_page():
    # 실측(2026년 8월호 "요약" 장 1쪽) — 성장률·물가·고용 세 줄이 마침표도
    # 빈 줄도 없이 붙어 있어, rationale.sentences 가 셋을 한 "문장"으로
    # 묶는다(예전엔 이게 표 쪽 근처로만 근거 수집 창을 좁히는 이유였다).
    from domains.forecast.pipeline import rationale
    headline = (FIXTURES / "kdi_2026-08_p1_headline_summary.txt").read_text(encoding="utf-8")
    got_growth = rationale.pick(headline, "gdp_growth")
    got_emp = rationale.pick(headline, "emp_change")
    assert got_growth is not None
    assert got_growth == got_emp  # 서로 다른 지표인데 같은 "문장"이 뽑힌다
