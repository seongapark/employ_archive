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


class _Resp:
    def __init__(self, text="", content=b""):
        self.text, self.content = text, content


def test_collect_issue_rationales_returns_empty_for_the_real_report(monkeypatch):
    # 실제 원문(PAGE)의 성장률 서술("… 투자 및 수출 증가세가 이어지면서
    # 2.5% 내외 성장률이 예상")에는 인과 표지가 없다(실측) — 그래서
    # gdp_growth 근거가 안 나오는 게 이 회차의 실제 모습이다.
    monkeypatch.setattr(kiet.http, "get", lambda url, **kw: _Resp(
        text='<a href="/common/file/userDownload?atch_no=x">첨부</a>', content=b"%PDF"))
    monkeypatch.setattr(kiet.pdf, "page_texts", lambda data: [PAGE])

    assert kiet.collect_issue_rationales(ISSUE) == []


def test_collect_issue_rationales_excludes_indicators_this_table_does_not_carry(monkeypatch):
    # 같은 쪽에 물가(cpi) 조건을 다 만족하는 문장이 있다(실측: "민간소비는
    # 실질소득 증가와 … 2.2% 증가할 것으로 예상"). 하지만 이 표에는 성장률만
    # 있으므로(머리말 참고) cpi 근거로 저장되면 안 된다.
    from domains.forecast.pipeline import rationale
    assert rationale.pick(PAGE, "cpi") is not None  # 전제 확인: 문장 자체는 실재한다

    monkeypatch.setattr(kiet.http, "get", lambda url, **kw: _Resp(
        text='<a href="/common/file/userDownload?atch_no=x">첨부</a>', content=b"%PDF"))
    monkeypatch.setattr(kiet.pdf, "page_texts", lambda data: [PAGE])

    got = kiet.collect_issue_rationales(ISSUE)
    assert "cpi" not in {r.indicator for r in got}


def test_collect_issue_rationales_finds_a_qualifying_growth_sentence(monkeypatch):
    # 자리 표시자 문장이다 — 실제 원문(PAGE)의 성장률 서술에는 인과 표지가
    # 없어(위 테스트 참고) 근거가 안 나온다. 이 테스트는 인과 표지가 있는
    # 문장이 있을 때 메커니즘이 정말 뽑아내고 실제 쪽 번호로 인용하는지만
    # 확인한다.
    prefix = "○ 성장률은 반도체 수출 호조에 힘입어 2.5% 내외로 상향조정될 것으로 전망된다.\n"
    page_with_sentence = prefix + PAGE

    monkeypatch.setattr(kiet.http, "get", lambda url, **kw: _Resp(
        text='<a href="/common/file/userDownload?atch_no=x">첨부</a>', content=b"%PDF"))
    monkeypatch.setattr(kiet.pdf, "page_texts", lambda data: ["표지", page_with_sentence])

    got = kiet.collect_issue_rationales(ISSUE)
    by_ind = {r.indicator: r for r in got}
    assert "gdp_growth" in by_ind
    assert by_ind["gdp_growth"].source_page == 2   # 실제로 찾은 쪽(표지 다음)
    assert by_ind["gdp_growth"].org == "KIET"


def test_collect_issue_rationales_returns_empty_when_no_table_found(monkeypatch):
    monkeypatch.setattr(kiet.http, "get", lambda url, **kw: _Resp(
        text='<a href="/common/file/userDownload?atch_no=x">첨부</a>', content=b"%PDF"))
    monkeypatch.setattr(kiet.pdf, "page_texts", lambda data: ["표지", "본문"])

    assert kiet.collect_issue_rationales(ISSUE) == []
