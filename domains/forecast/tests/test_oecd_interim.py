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


def test_pick_finds_a_generic_global_sentence_that_is_not_about_korea():
    # 실측(2026년 3월호 20쪽) — G20·중국·인도 얘기이지 한국 얘기가 아니다.
    # 이 문장을 한국의 근거로 저장하면 표 쪽 번호를 잘못 인용하는 것보다
    # 더 나쁘다 — 아예 다른 나라 얘기를 한국 근거로 둔갑시키는 것이다.
    #
    # 이 쪽의 문단은 "20. " 처럼 번호로 시작한다. 절 번호를 각주 갈래로
    # (줄째) 버리면 이 문장이 머리를 잃어 이 단언이 조용히 통과해 버린다 —
    # 규칙이 나아져서가 아니라 문장이 반토막 나서 안 걸리는 것이므로,
    # 그때는 이 테스트가 창의 좁음을 더는 못 지킨다. 절 번호를 불릿 갈래로
    # 두는 이유 중 하나가 이것이다(test_rationale.py 의
    # test_section_heading_keeps_the_head_line_of_a_numbered_oecd_paragraph).
    from domains.forecast.pipeline import rationale
    global_text = load("oecd_interim_2026-03_p20_global.txt")
    got = rationale.pick(global_text, "gdp_growth")
    assert got is not None
    assert "korea" not in got.lower()
