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


def test_aggregate_columns_are_not_mistaken_for_industries(records):
    # '광공업'과 '사회간접자본 및 기타서비스'는 집계 열이다. 산업으로 들어오면
    # 제조업·서비스업이 이중 계상된다.
    assert all(r.category != "광공업" for r in records if r.category)
    manufacturing = [r for r in records
                     if r.breakdown == "industry" and r.category == "C"]
    assert manufacturing
    newest = max(manufacturing, key=lambda r: r.period)
    assert 3000 < newest.value < 5500     # 제조업 취업자 400만명대


def test_carries_year_over_year_change(records):
    industry = [r for r in records if r.breakdown == "industry" and r.yoy is not None]
    assert industry
    assert any(r.yoy < 0 for r in industry)   # 감소한 산업이 있다


def test_ids_are_unique(records):
    ids = [r.id for r in records]
    assert len(ids) == len(set(ids))
