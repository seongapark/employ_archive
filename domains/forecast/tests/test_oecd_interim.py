from datetime import date
from pathlib import Path

import pytest

from domains.forecast.pipeline.collectors import oecd_interim as oi

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_reads_the_rotated_growth_table():
    # 표가 90도로 놓여 국가명이 'K o re a' 로, 값이 한 줄에 하나씩 나온다
    rows, blocks = oi.parse_rotated_table(load("oecd_interim_2026-03_p8.txt"))
    assert rows[10] == "Korea"
    assert len(rows) == len(blocks[0])
    assert blocks[0][10] == 1.7   # 2026 전망
    assert blocks[1][10] == -0.4  # 12월 EO 대비 차이


def test_refuses_a_table_whose_rows_and_values_disagree():
    # 라벨 한 줄이 사라지면 인덱스가 밀려 조용히 다른 나라 값이 된다
    broken = load("oecd_interim_2026-03_p8.txt").replace("J a p a n\n", "")
    with pytest.raises(ValueError):
        oi.parse_rotated_table(broken)


def test_indicator_comes_from_the_table_caption():
    assert oi.table_indicator(load("oecd_interim_2026-03_p8.txt")) == "gdp_growth"
    assert oi.table_indicator(load("oecd_interim_2026-03_p9.txt")) == "cpi"
    # 근원물가는 우리 지표가 아니다
    assert oi.table_indicator(load("oecd_interim_2026-03_p10.txt")) is None


def test_korea_values_carry_the_forecast_years():
    got = oi.korea_values(load("oecd_interim_2026-03_p8.txt"), date(2026, 3, 26))
    assert got == {2026: 1.7, 2027: 2.1}


def test_the_same_shape_reads_the_earlier_editions():
    assert oi.korea_values(load("oecd_interim_2025-09_p7.txt"), date(2025, 9, 23))[2026] is not None
    assert oi.korea_values(load("oecd_interim_2025-03_p7.txt"), date(2025, 3, 17))[2026] is not None


def test_parse_builds_records_for_one_edition():
    pages = {8: load("oecd_interim_2026-03_p8.txt"), 9: load("oecd_interim_2026-03_p9.txt"),
             10: load("oecd_interim_2026-03_p10.txt")}
    records = oi.parse(pages, "March 2026", date(2026, 3, 26), "https://x/y.pdf")
    got = {(r.indicator, r.target_year): r for r in records}
    assert got[("gdp_growth", 2026)].value == 1.7
    assert got[("cpi", 2026)].value == 2.7
    assert ("emp_change", 2026) not in got  # Interim 에는 고용 지표가 없다
    r = got[("gdp_growth", 2026)]
    assert r.org == "OECD"
    assert r.published_at == date(2026, 3, 26)
    assert r.id == "oecd-2026-03-gdp_growth-2026"
    assert r.confidence == "extracted"  # PDF 에서 뽑았다 — API 의 verified 와 구분한다
    assert r.report_title == "OECD Economic Outlook, Interim Report March 2026"


def test_editions_are_listed_with_their_publication_dates():
    assert oi.EDITIONS["March 2026"][0] == date(2026, 3, 26)
    assert oi.EDITIONS["September 2025"][0] == date(2025, 9, 23)
    assert oi.EDITIONS["March 2025"][0] == date(2025, 3, 17)
    for label, (pub, url) in oi.EDITIONS.items():
        assert url.startswith("https://www.oecd.org/"), label


def test_a_page_that_only_mentions_a_table_is_skipped():
    # 목차와 본문 참조에도 "Table 1. Global growth..." 캡션이 나온다.
    # 그 페이지에서 실패하면 진짜 표가 실린 페이지를 못 본다.
    toc = "Table 1. Global growth is projected to moderate 6\nTable 2. Headline inflation 7\n"
    pages = {5: toc, 8: load("oecd_interim_2026-03_p8.txt")}
    records = oi.parse(pages, "March 2026", date(2026, 3, 26), "https://x/y.pdf")
    assert {(r.indicator, r.target_year) for r in records} == {
        ("gdp_growth", 2026), ("gdp_growth", 2027)}


def test_parse_fails_when_no_page_yields_a_table():
    with pytest.raises(ValueError, match="전망표"):
        oi.parse({5: "Table 1. Global growth 6\n"}, "March 2026", date(2026, 3, 26), "u")


class _Resp:
    def __init__(self, content=b""):
        self.content = content


def _wire(monkeypatch, pages_list):
    monkeypatch.setattr(oi.http, "get", lambda url, **kw: _Resp(content=b"%PDF"))
    monkeypatch.setattr(oi.pdf, "page_texts", lambda data: pages_list)


def test_collect_edition_rationales_returns_empty_for_the_real_report(monkeypatch):
    # 실제 원문(8·9쪽 성장률·물가 표)과 그 앞뒤(7·10쪽 상당)에는 근거가
    # 없다 — 표만 있는 쪽이라 문장 자체가 없다.
    pages = ["표지"] * 7 + [
        load("oecd_interim_2026-03_p8.txt"),
        load("oecd_interim_2026-03_p9.txt"),
        load("oecd_interim_2026-03_p10.txt"),
        "결론",
    ]
    _wire(monkeypatch, pages)
    assert oi.collect_edition_rationales("March 2026") == []


def test_collect_edition_rationales_reads_the_page_before_the_growth_table(monkeypatch):
    # 자리 표시자 문장이다 — 실제 보고서에는 한국만 따로 짚는 서술이 없다
    # (아래 global 테스트 참고). 이 테스트는 창이 정말 표 앞쪽 한 쪽을
    # 읽는지만 확인한다.
    prose = "한국 성장률은 반도체 수출 호조에 힘입어 상향조정될 것으로 전망된다."
    pages = ["표지"] * 6 + [
        prose,
        load("oecd_interim_2026-03_p8.txt"),
        load("oecd_interim_2026-03_p9.txt"),
    ]
    _wire(monkeypatch, pages)

    got = oi.collect_edition_rationales("March 2026")
    by_ind = {r.indicator: r for r in got}
    assert "gdp_growth" in by_ind
    assert by_ind["gdp_growth"].source_page == 7   # 표 쪽(8)이 아니라 앞쪽(7)
    assert by_ind["gdp_growth"].org == "OECD"
    assert by_ind["gdp_growth"].published_at == date(2026, 3, 26)


def test_collect_edition_rationales_reads_the_page_after_the_cpi_table(monkeypatch):
    prose = "물가는 국제유가 상승의 영향으로 당초 전망보다 높아질 것으로 예상된다."
    pages = [
        load("oecd_interim_2026-03_p8.txt"),
        load("oecd_interim_2026-03_p9.txt"),
        prose,
    ]
    _wire(monkeypatch, pages)

    got = oi.collect_edition_rationales("March 2026")
    by_ind = {r.indicator: r for r in got}
    assert "cpi" in by_ind
    assert by_ind["cpi"].source_page == 3   # 표 쪽(2)이 아니라 뒤쪽(3)


def test_collect_edition_rationales_returns_empty_when_no_table_found(monkeypatch):
    _wire(monkeypatch, ["표지", "본문"])
    assert oi.collect_edition_rationales("March 2026") == []


def test_the_generic_global_page_no_longer_yields_a_rationale_at_all():
    # 이 테스트는 예전에 반대 방향을 단언했다 — 20쪽에서 "Economic growth in
    # the G20 emerging-market economies is projected to ease somewhat, largely
    # due to a step down in growth in China and India." 가 gdp_growth 근거로
    # **뽑힌다**는 것을 못박아, 창을 표 쪽 ±1 로 좁혀 둔 이유를 보였다.
    #
    # 절 제목 규칙(_SECTION_HEADING, `^\s*\d+\.\s`)을 넣은 뒤로 이 두 문장은
    # 더는 뽑히지 않는다. 이 쪽의 OECD 본문은 문단마다 "20. "·"21. " 처럼
    # 번호가 붙는 문체라, 그 규칙이 문단 첫 줄을 절 제목으로 보고 버린다.
    # **이것이 그 규칙이 지는 비용이고, 여기 그대로 기록해 둔다** — 잃은 게
    # 마침 이 아카이브가 저장하면 안 되는 문장(한국이 아니라 G20 전체 서술)
    # 이었다는 건 다행이지 설계가 아니다. 자세한 실측은 rationale.py 의
    # _SECTION_HEADING 옆 주석과 test_rationale.py 의 같은 이름 절 참고.
    #
    # 창을 좁혀 두는 이유 자체는 그대로다 — collect_edition_rationales 문서
    # 주석이 24쪽 미국 정책금리 문장도 같은 부류로 실측해 두었고, 그 쪽은
    # 픽스처로 박제돼 있지 않다.
    from domains.forecast.pipeline import rationale
    global_text = load("oecd_interim_2026-03_p20_global.txt")
    assert rationale.pick(global_text, "gdp_growth") is None
    assert rationale.pick(global_text, "cpi") is None
