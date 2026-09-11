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


def test_coverage_check_fails_when_the_total_row_vanishes(records):
    # TOTAL_COLUMN 철자가 바뀌면 총괄 행이 통째로 빠진다 — 산업별 표는
    # 가득 찬 채 총괄 화면만 빈다
    latest = max(r.period for r in records)
    thinned = [r for r in records
               if not (r.period == latest and r.breakdown == "total")]
    with pytest.raises(ValueError, match="전체"):
        eaps.check_coverage(thinned)


def _shift(period: str, months: int) -> str:
    year, month = (int(x) for x in period.split("-"))
    total = year * 12 + (month - 1) - months
    return f"{total // 12}-{total % 12 + 1:02d}"


def test_freshness_check_fails_when_the_series_is_truncated(records):
    from datetime import date as _date
    # 파싱이 조용히 잘리면 check_coverage 는 못 잡는다 — 여기서 잡아야 한다.
    latest = max(r.period for r in records)
    year, month = (int(x) for x in latest.split("-"))
    # 남은 최신월이 MAX_MONTHS_BEHIND 보다 더 뒤처지도록 충분히 잘라낸다.
    cutoff = _shift(latest, eaps.MAX_MONTHS_BEHIND + 1)
    truncated = [r for r in records if r.period <= cutoff]
    with pytest.raises(ValueError, match="뒤처졌다"):
        eaps.check_freshness(truncated, _date(year, month, 28))


def test_freshness_check_passes_on_a_current_series(records):
    from datetime import date as _date
    latest = max(r.period for r in records)
    year, month = (int(x) for x in latest.split("-"))
    eaps.check_freshness(records, _date(year, month, 28))


def test_collects_sex_and_age_for_the_latest_month(records):
    latest = max(r.period for r in records)
    sex = {r.category: r for r in records if r.period == latest and r.breakdown == "sex"}
    age = {r.category: r for r in records if r.period == latest and r.breakdown == "age"}
    assert set(sex) == {"M", "F"}
    assert set(age) == {"15-29", "30-39", "40-49", "50-59", "60+"}
    assert sex["M"].value == 16079.5      # 2026-07 남자 취업자(천명)
    assert sex["M"].yoy == 47.9


def test_sex_and_age_sum_to_the_total(records):
    """부분집합 열(15∼19·20∼29·65/70/75세이상)을 넣으면 합이 깨진다.

    원자료가 반올림된 값이라 합이 총계와 정확히 같지는 않다(실측 편차 최대 0.1천명).
    허용오차 0.2 는 가장 작은 부분집합 열(15∼19, 151.6천명)이 섞이기만 해도 즉시
    깨지므로 판별력을 잃지 않는다.
    """
    for period in ("2026-07", "2025-12"):
        total = next(r for r in records if r.period == period and r.breakdown == "total")
        for breakdown in ("sex", "age"):
            parts = [r for r in records if r.period == period and r.breakdown == breakdown]
            assert parts, f"{period} {breakdown} 레코드가 없다"
            assert abs(sum(p.value for p in parts) - total.value) <= 0.2


def test_coverage_guard_fails_when_an_age_band_is_missing(records):
    kept = [r for r in records if not (r.breakdown == "age" and r.category == "60+")]
    with pytest.raises(ValueError, match="연령"):
        eaps.check_coverage(kept)


# ── 총괄 지표 (1.전체 · 1564 · 1529) ──────────────────────────────────

@pytest.fixture(scope="module")
def totals():
    return eaps.parse_totals(
        FIXTURE.read_bytes(),
        released_at=date(2026, 8, 12),
        release_url="https://mods.go.kr/x",
        attachments=[],
        collected_at=datetime(2026, 8, 30, 9, 0),
    )


def pick(records, series, breakdown="total", category=None, period="2026-07"):
    hits = [r for r in records if r.series == series and r.breakdown == breakdown
            and r.category == category and r.period == period]
    assert len(hits) == 1, (series, breakdown, category, period, len(hits))
    return hits[0]


def test_reads_the_headline_rates_the_release_leads_with(totals):
    # 2026년 7월 회차의 보도자료 요약이 말하는 숫자들이다.
    assert pick(totals, "employment_rate", "scope", "15-64").value == 70.3
    assert pick(totals, "employment_rate", "scope", "15-29").value == 44.2
    assert pick(totals, "unemployment_rate").value == 2.6
    assert pick(totals, "unemployment_rate", "scope", "15-29").value == 6.8


def test_rates_are_percent_and_their_change_is_percentage_points(totals):
    r = pick(totals, "employment_rate", "scope", "15-64")
    assert r.unit == "%"
    assert r.yoy == 0.1              # 증감 시트에 적힌 %p. 우리가 빼서 만들지 않는다.


def test_levels_stay_in_thousands(totals):
    assert pick(totals, "unemployed").unit == "천명"
    assert pick(totals, "unemployed").value == 776.1
    assert pick(totals, "inactive").value == 16102.6
    assert pick(totals, "population").value == 46014.8
    assert pick(totals, "labor_force").value == 29912.2


def test_the_change_comes_from_the_paired_delta_sheet(totals):
    # 취업자 +107.6천명 = 보도자료의 `10만 7천명 증가`
    assert pick(totals, "labor_force").yoy == 158.0
    assert pick(totals, "unemployed").yoy == 50.4


def test_does_not_re_emit_the_total_headcount(totals):
    """취업자수 전체는 산업 시트가 만든다. 두 곳에서 만들면 같은 id 를 두 번
    쓰게 되고, 언젠가 둘이 어긋나면 어느 쪽이 이겼는지 아무도 모른다."""
    assert not [r for r in totals if r.series == "headcount" and r.breakdown == "total"]


def test_still_carries_headcount_for_the_age_scopes(totals):
    # 15~64세·15~29세 취업자수는 산업 시트에 없다 — 여기서만 나온다.
    assert pick(totals, "headcount", "scope", "15-64").value == 24519.5
    assert pick(totals, "headcount", "scope", "15-29").value == 3441.2


def test_the_two_sheets_agree_on_the_total_headcount():
    """`1.전체` 와 `3.산업(신)` 이 같은 취업자수를 말하는지 확인한다.

    어긋나면 우리가 두 시트를 섞어 쓰고 있다는 뜻이고, 화면의 카드와 지표가
    서로 다른 숫자를 말하게 된다. 2026-07 회차에서 28개월이 전부 일치했다.
    """
    data = FIXTURE.read_bytes()
    assert eaps.total_headcount_matches(data) is True


def test_ids_never_collide_with_the_headcount_records(records, totals):
    assert not ({r.id for r in totals} & {r.id for r in records})


def test_every_month_is_contiguous(totals):
    """회차마다 앞쪽 몇 행은 연도별 8월이라 띄엄띄엄하다. 그 구간을 시계열로
    그리면 2년 간격이 한 칸으로 붙어 급변한 것처럼 보인다."""
    months = sorted({r.period for r in totals})
    def nxt(p):
        y, m = int(p[:4]), int(p[5:7]) + 1
        return f"{y + 1}-01" if m > 12 else f"{y}-{m:02d}"
    assert all(nxt(a) == b for a, b in zip(months, months[1:])), months


def test_parse_totals_stops_when_the_two_sheets_disagree(monkeypatch):
    """교차 확인은 적어만 두면 소용없다 — 어긋나면 수집이 멈춰야 한다.

    어긋난 채로 통과시키면 카드는 산업 시트의 취업자수를, 지표는 총괄 시트의
    숫자를 말하게 되고 둘이 다른데도 화면은 아무 말을 하지 않는다.
    """
    monkeypatch.setattr(eaps, "total_headcount_matches", lambda data: False)
    with pytest.raises(ValueError, match="취업자수"):
        eaps.parse_totals(FIXTURE.read_bytes(), released_at=date(2026, 8, 12),
                          release_url="https://mods.go.kr/x", attachments=[],
                          collected_at=datetime(2026, 8, 30, 9, 0))
