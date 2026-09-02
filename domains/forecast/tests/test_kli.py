from datetime import date
from pathlib import Path

import pytest

from domains.forecast.pipeline.collectors import kli

FIXTURES = Path(__file__).parent / "fixtures"
PAGE = (FIXTURES / "kli_2026_forecast.txt").read_text(encoding="utf-8")
ISSUE = kli.Issue("2025년 노동시장 평가와 2026년 노동시장 전망", date(2026, 1, 2),
                  "https://www.kli.re.kr/board.es?list_no=147627")


def by_key(records):
    return {(r.indicator, r.target_year, r.target_period): r for r in records}


def test_table_block_excludes_the_caption_and_the_prose_around_it():
    # 표 앞뒤로 서술이 길게 붙어 있어 페이지를 통째로 넘기면 헤더를 잘못 잡는다.
    # 캡션도 빼야 한다 — "...하반기 및 ... 연간 고용 전망" 의 기간 낱말이
    # 헤더로 딸려 들어가면 열 복원이 어긋난다.
    block = kli.forecast_table(PAGE)
    assert "고용 전망" not in block          # 캡션 제외
    assert "상반기 하반기p 연간p" in block    # 진짜 헤더는 남는다
    assert "취업자" in block
    assert "인구추계" not in block           # 표 뒤 본문도 들어오면 안 된다


def test_parse_reads_the_employment_forecast():
    got = by_key(kli.parse(PAGE, ISSUE, "https://x/y.pdf", 24))
    assert got[("emp_change", 2026, "annual")].value == 21.0   # 210천명 -> 21.0만명
    assert got[("unemp_rate", 2026, "annual")].value == 2.8
    assert got[("emp_rate", 2026, "annual")].value == 63.1


def test_parse_keeps_the_half_year_columns():
    got = by_key(kli.parse(PAGE, ISSUE, "https://x/y.pdf", 24))
    assert got[("emp_change", 2026, "h1")].value == 22.0
    assert got[("emp_change", 2026, "h2")].value == 20.0
    assert got[("emp_rate", 2026, "h1")].value == 62.9


def test_parse_drops_years_before_publication():
    years = {r.target_year for r in kli.parse(PAGE, ISSUE, "https://x/y.pdf", 24)}
    assert years == {2026}


def test_parse_record_fields():
    r = by_key(kli.parse(PAGE, ISSUE, "https://x/y.pdf", 24))[("emp_change", 2026, "annual")]
    assert r.org == "KLI"
    assert r.org_name_ko == "한국노동연구원"
    assert r.unit == "만명"
    assert r.confidence == "extracted"
    assert r.published_at == date(2026, 1, 2)
    assert r.id == "kli-2026-01-emp_change-2026"


def test_parse_omits_indicators_the_report_does_not_forecast():
    inds = {r.indicator for r in kli.parse(PAGE, ISSUE, "https://x/y.pdf", 24)}
    assert "gdp_growth" not in inds  # 노동시장 전망이라 성장률·물가는 없다
    assert "cpi" not in inds


def test_forecast_table_raises_when_the_caption_is_missing():
    with pytest.raises(ValueError):
        kli.forecast_table("표가 없는 페이지 본문")


