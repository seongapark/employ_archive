from datetime import date
from pathlib import Path

import pytest

from domains.forecast.pipeline.collectors import kiet

PAGE = (Path(__file__).parent / "fixtures" / "kiet_2026h2_macro.txt").read_text(encoding="utf-8")
ISSUE = kiet.Issue("2026년 하반기 경제·산업 전망", date(2026, 5, 26),
                   "https://www.kiet.re.kr/trends/ecolookView?ecolook_no=56")


def by_key(records):
    return {(r.indicator, r.target_year, r.target_period): r for r in records}


def test_table_block_excludes_the_caption_and_surrounding_prose():
    block = kiet.macro_table(PAGE)
    assert "국내 주요 거시경제지표 전망" not in block
    assert "연간 상반기 하반기 연간" in block
    assert "실질GDP" in block
    assert "자료:" not in block


def test_parse_reads_the_growth_forecast():
    got = by_key(kiet.parse(PAGE, ISSUE, "https://x/y.pdf", 36))
    assert got[("gdp_growth", 2026, "annual")].value == 2.5
    assert got[("gdp_growth", 2026, "h1")].value == 2.9
    assert got[("gdp_growth", 2026, "h2")].value == 2.1


def test_parse_drops_years_before_publication():
    assert {r.target_year for r in kiet.parse(PAGE, ISSUE, "https://x/y.pdf", 36)} == {2026}


def test_parse_omits_indicators_the_table_does_not_carry():
    inds = {r.indicator for r in kiet.parse(PAGE, ISSUE, "https://x/y.pdf", 36)}
    assert inds == {"gdp_growth"}  # 이 표에는 취업자·실업률·물가가 없다


def test_parse_record_fields():
    r = by_key(kiet.parse(PAGE, ISSUE, "https://x/y.pdf", 36))[("gdp_growth", 2026, "annual")]
    assert r.org == "KIET"
    assert r.org_name_ko == "산업연구원"
    assert r.published_at == date(2026, 5, 26)
    assert r.id == "kiet-2026-05-gdp_growth-2026"


def test_parse_list_keeps_the_outlook_issues_only():
    # 제목은 <a> 안의 <strong> 에 들어 있다
    html = (
        '<a href="./ecolookView?ecolook_no=56&skey="><strong>2026년 하반기 경제·산업 전망</strong></a>'
        '<a href="./ecolookView?ecolook_no=57&skey="><strong>2026년 하반기 경제·산업 전망 : 13대 주력산업편</strong></a>'
        '<a href="./ecolookView?ecolook_no=54&skey="><strong>2026년 경제·산업 전망</strong></a>'
    )
    issues = kiet.parse_list(html)
    # 산업편은 거시 전망표가 없다 — 걸러야 한다
    assert [i.url.rsplit("=", 1)[1] for i in issues] == ["56", "54"]


def test_issue_date_comes_from_the_page_metadata():
    assert kiet.issue_date('"datePublished": "2026.05.26",') == date(2026, 5, 26)
    with pytest.raises(ValueError):
        kiet.issue_date("<html>날짜 없음</html>")


def test_collect_issue_skips_the_table_of_contents(monkeypatch):
    # 표 차례에도 "<표 1-6> 국내 주요 거시경제지표 전망……36" 이 나온다.
    # 거기서 실패하면 진짜 표가 실린 쪽을 못 본다.
    toc = "표 차례\n<표 1-6> 국내 주요 거시경제지표 전망·········36\n"

    class _Resp:
        def __init__(self, text="", content=b""):
            self.text, self.content = text, content

    monkeypatch.setattr(kiet.http, "get", lambda url, **kw: _Resp(
        text='<a href="/common/file/userDownload?atch_no=x">첨부</a>', content=b"%PDF"))
    monkeypatch.setattr(kiet.pdf, "page_texts", lambda data: [toc, PAGE])

    records = kiet.collect_issue(ISSUE)
    assert {(r.indicator, r.target_year) for r in records} == {("gdp_growth", 2026)}
    assert records[0].source_page == 2
