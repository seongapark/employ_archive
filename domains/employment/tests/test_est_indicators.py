"""사업체노동력조사 총괄 지표(상용·임시일용·입직·이직·빈일자리).

종사자수(headcount)만 받던 수집기에 같은 KOSIS 표의 항목 여덟을 더 읽는다.
최신월은 KOSIS 가 한 달 늦어 보도자료 hwpx 에서 보충한다(빈일자리는 보도자료에 없다).
"""
import json
from datetime import date, datetime
from pathlib import Path

import pytest

from domains.employment.pipeline.collectors import est

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def rows():
    return json.loads((FIX / "est_kosis_totals.json").read_text(encoding="utf-8"))


def _parse(rows):
    return est.parse_totals(rows, released_at=date(2026, 9, 30), release_url=est.STAT_URL,
                            collected_at=datetime(2026, 9, 30, 15, 0))


def _get(records, series, period):
    return next(r for r in records if r.series == series and r.period == period)


def test_totals_cover_eight_indicators_for_every_month(rows):
    records = _parse(rows)
    assert {r.series for r in records} == set(est.TOTAL_ITEMS_SERIES)
    assert all(r.breakdown == "total" and r.category is None for r in records)
    per_month = {}
    for r in records:
        per_month.setdefault(r.period, set()).add(r.series)
    assert all(len(s) == 8 for s in per_month.values())


def test_counts_are_thousands_and_rates_are_percent(rows):
    records = _parse(rows)
    regular = _get(records, "regular", "2026-07")
    assert (regular.value, regular.unit) == (17280.1, "천명")
    rate = _get(records, "entry_rate", "2026-07")
    assert (rate.value, rate.unit) == (5.9, "%")


def test_year_over_year_is_value_minus_the_same_month_a_year_earlier(rows):
    records = _parse(rows)
    # 2025-07 입직자 966.0, 2026-07 1142.6 — 보도자료의 증감 177 과 반올림만큼 같다
    assert _get(records, "entered", "2026-07").yoy == pytest.approx(176.6)
    # 비율의 증감은 %p 다
    assert _get(records, "entry_rate", "2026-07").yoy == pytest.approx(0.8)
    assert _get(records, "entry_rate", "2024-07").yoy is None


def test_ids_carry_the_indicator_so_they_never_collide_with_headcount(rows):
    records = _parse(rows)
    ids = [r.id for r in records]
    assert len(ids) == len(set(ids))
    assert "est-2026-07-regular-total" in ids


def test_an_item_whose_name_changed_is_refused(rows):
    # 코드는 그대로인데 항목이 바뀌면(개편) 조용히 다른 숫자를 싣게 된다
    broken = [dict(r, ITM_NM="근로자_기타") if r["ITM_ID"] == "16118MF_2" else r for r in rows]
    with pytest.raises(ValueError, match="항목"):
        _parse(broken)


def test_a_missing_indicator_in_the_latest_month_is_refused(rows):
    latest = max(r["PRD_DE"] for r in rows)
    broken = [r for r in rows if not (r["PRD_DE"] == latest and r["ITM_ID"] == "16118MP_13")]
    with pytest.raises(ValueError, match="exit_rate"):
        est.check_totals(_parse(broken))


# ── 보도자료 최신월 ──────────────────────────────────────────────────────

def _release():
    return est.parse_release_totals(
        (FIX / "est_2026-07.hwpx").read_bytes(), period="2026-07",
        released_at=date(2026, 8, 27), release_url="https://www.moel.go.kr/x",
        attachments=[], collected_at=datetime(2026, 8, 27, 9, 0))


def test_release_gives_workers_and_turnover_with_the_published_changes():
    got = {r.series: (r.value, r.unit, r.yoy) for r in _release()}
    assert got == {
        "regular": (17280.0, "천명", 78.0),
        "temporary": (2071.0, "천명", 147.0),
        "entered": (1143.0, "천명", 177.0),
        "exited": (1127.0, "천명", 178.0),
        "entry_rate": (5.9, "%", 0.9),     # 원문 증감 — 반올림 값끼리 빼면 0.8 이 된다
        "exit_rate": (5.8, "%", 0.9),
    }
    assert {r.period for r in _release()} == {"2026-07"}


def test_release_of_another_month_is_refused():
    # 그 달 표가 없으면 필요한 지표를 하나도 못 읽어 실패한다
    with pytest.raises(ValueError, match="못 읽었다"):
        est.parse_release_totals(
            (FIX / "est_2026-07.hwpx").read_bytes(), period="2026-08",
            released_at=date(2026, 8, 27), release_url="https://www.moel.go.kr/x",
            attachments=[], collected_at=datetime(2026, 8, 27, 9, 0))
