from datetime import date, datetime
from pathlib import Path

import pytest

from domains.employment.pipeline.collectors import eaps

FIXTURE = Path(__file__).parent / "fixtures" / "eaps_2026-07.xlsx"


@pytest.fixture(scope="module")
def records():
    return eaps.parse(
        FIXTURE.read_bytes(),
        released_at=date(2026, 8, 12),
        release_url="https://mods.go.kr/board.es?mid=a10301030100&bid=a103010301&list_no=446465&act=view",
        attachments=[],
        collected_at=datetime(2026, 8, 30, 9, 0),
    )


def test_every_record_is_eaps_in_thousands(records):
    assert records
    assert {r.source for r in records} == {"eaps"}
    assert {r.unit for r in records} == {"천명"}


def test_produces_a_total_for_the_latest_month(records):
    totals = [r for r in records if r.breakdown == "total"]
    assert totals
    newest = max(totals, key=lambda r: r.period)
    # 2026년 취업자는 2,800만명대 — 천명 단위로 28,000 언저리
    assert 26000 < newest.value < 30000


def test_industry_categories_are_ksic_major_codes(records):
    codes = {r.category for r in records if r.breakdown == "industry"}
    assert codes <= set("ACDEFGHIJKLMNOPQRSTU")
    assert {"C", "F", "Q"} <= codes


def test_mining_is_absent_because_the_release_folds_it_into_manufacturing(records):
    # 보도자료는 광업을 '광공업'에 묶어 단독 제공하지 않는다
    assert "B" not in {r.category for r in records if r.breakdown == "industry"}


def test_industry_values_do_not_double_count(records):
    # '광공업'과 '사회간접자본 및 기타서비스'는 집계 열이다. 산업으로 새어
    # 들어오면 제조업·서비스업이 이중 계상돼 산업별 합이 전체취업자를 넘는다.
    # 경활은 광업(B)만 빠지므로 정상이면 합이 전체보다 아주 조금 작다.
    latest = max(r.period for r in records)
    total = next(r.value for r in records
                 if r.breakdown == "total" and r.period == latest)
    parts = sum(r.value for r in records
                if r.breakdown == "industry" and r.period == latest)
    assert parts < total
    assert parts > total * 0.99


def test_reads_monthly_rows_not_annual_or_quarterly(records):
    # 같은 표에 연평균(단독 4자리) 과 분기('YYYY.Q/4') 행이 월별 행과 섞여
    # 있다. 연도가 바뀌는 월 시작 행에서만 연도가 붙고 그 뒤로는 숫자만 오므로,
    # 연도 문맥을 잘못 이어붙이면 최신월이 실제보다 낮은 연도로 주저앉거나
    # 서로 다른 실제월이 같은 period 로 겹쳐 덮어써진다.
    totals = [r for r in records if r.breakdown == "total"]
    periods = [r.period for r in totals]
    assert len(periods) == len(set(periods))
    assert max(periods) == "2026-07"


def test_carries_year_over_year_change(records):
    industry = [r for r in records if r.breakdown == "industry" and r.yoy is not None]
    assert industry
    assert any(r.yoy < 0 for r in industry)   # 감소한 산업이 있다


def test_ids_are_unique(records):
    ids = [r.id for r in records]
    assert len(ids) == len(set(ids))


def test_coverage_check_passes_on_a_complete_month(records):
    eaps.check_coverage(records)          # 예외가 나면 실패


def test_coverage_check_fails_loudly_when_an_industry_vanishes(records):
    # 헤더 철자가 바뀌어 산업이 빠지면 화면에서 빈 칸으로만 보인다
    latest = max(r.period for r in records)
    thinned = [r for r in records
               if not (r.period == latest and r.category == "C")]
    with pytest.raises(ValueError, match="빠진 산업"):
        eaps.check_coverage(thinned)
