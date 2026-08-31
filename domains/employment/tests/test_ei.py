from datetime import date, datetime
from pathlib import Path

import pytest

from domains.employment.pipeline import hwpx
from domains.employment.pipeline.collectors import ei

FIXTURE = Path(__file__).parent / "fixtures" / "ei_2026-07.hwpx"


@pytest.fixture(scope="module")
def data():
    return FIXTURE.read_bytes()


@pytest.fixture(scope="module")
def records(data):
    return ei.parse(
        data,
        released_at=date(2026, 8, 11),
        release_url="https://www.moel.go.kr/news/enews/report/enewsView.do?news_seq=19759",
        attachments=[],
        collected_at=datetime(2026, 8, 30, 9, 0),
    )


def test_finds_the_four_tables_by_content_not_position(data):
    level, level2, delta, delta2 = ei.find_tables(hwpx.tables(data))
    for t in (level, level2, delta, delta2):
        assert len(t) > 30
    # 수준은 크고 증감은 작다 — 순서가 뒤집히면 여기서 잡힌다
    assert float(level[-1][1].replace(",", "")) > 10000
    assert abs(float(delta[-1][1].replace(",", ""))) < 1000


def test_headline_delta_is_read_from_the_summary_box(data):
    # 픽스처가 다음 회차로 바뀌어도 깨지지 않도록 고정값 대신 자릿수로 본다.
    # 상시가입자 증감은 월 수십만명 규모라 천명 단위로 세 자리다.
    stated = ei.headline_delta(hwpx.tables(data))
    assert stated is not None
    assert 50 < abs(stated) < 900


def test_total_matches_the_summary_box(data, records):
    # 문서가 스스로 검증 대조점을 갖고 있다: 요약문의 증감 = 증감표의 전산업.
    stated = ei.headline_delta(hwpx.tables(data))
    totals = [r for r in records if r.breakdown == "total"]
    newest = max(totals, key=lambda r: r.period)
    assert newest.yoy == pytest.approx(stated, abs=1.0)
    assert 15000 < newest.value < 17000


def test_industry_codes_match_what_the_release_covers(records):
    codes = {r.category for r in records if r.breakdown == "industry"}
    assert codes == set("ACDEFGHIJKLMNOPQRS")
    # 광업·가구내고용·국제기관은 '기타'로 묶여 단독 제공되지 않는다
    assert not ({"B", "T", "U"} & codes)


def test_aggregate_columns_are_excluded(data):
    # '서비스업'과 '기타*'는 집계 열이다. 대분류로 넣으면 이중 계상된다.
    level, cont, _, _ = ei.find_tables(hwpx.tables(data))
    assert level[0][6] == "서비스업"          # 앞 표 6번 열은 집계
    assert 6 not in ei.LEAD_COLUMNS
    assert cont[1][11] == "기타*"             # 이어지는 표 11번 열은 집계
    assert 11 not in ei.CONT_COLUMNS


def test_layout_check_rejects_a_changed_header(data):
    level, cont, _, _ = ei.find_tables(hwpx.tables(data))
    broken = [list(r) for r in level]
    broken[0][2] = "뭔가다른것"
    with pytest.raises(ValueError, match="열 배치"):
        ei.check_layout(broken, cont)


def test_every_record_is_ei_in_thousands(records):
    assert {r.source for r in records} == {"ei"}
    assert {r.unit for r in records} == {"천명"}


def test_ids_are_unique(records):
    ids = [r.id for r in records]
    assert len(ids) == len(set(ids))


def test_reads_every_month_in_the_table_not_just_the_latest(records):
    # 표는 28개월치를 담고 있다. 마지막 행만 읽으면 24개월 시계열을 모으는 데
    # 2년이 걸린다.
    totals = [r for r in records if r.breakdown == "total"]
    periods = [r.period for r in totals]
    assert len(periods) == len(set(periods)), "같은 기간이 여러 번 나왔다"
    assert len(periods) >= 24
    assert max(periods) >= "2026-01"


def test_industry_sum_tracks_the_total(records):
    # 열이 밀리거나 집계 열('서비스업', '기타*')이 섞이면 합이 전체에서 벗어난다.
    latest = max(r.period for r in records)
    total = next(r.value for r in records
                 if r.breakdown == "total" and r.period == latest)
    parts = sum(r.value for r in records
                if r.breakdown == "industry" and r.period == latest)
    # 광업·가구내고용·국제기관이 '기타'로 빠지므로 합이 전체보다 조금 작다
    assert 0.97 < parts / total < 1.0


def test_coverage_check_passes_on_a_complete_month(records):
    ei.check_coverage(records)


def test_coverage_check_fails_loudly_when_an_industry_vanishes(records):
    latest = max(r.period for r in records)
    thinned = [r for r in records
               if not (r.period == latest and r.category == "C")]
    with pytest.raises(ValueError, match="빠진 산업"):
        ei.check_coverage(thinned)


def test_coverage_check_fails_when_the_total_row_vanishes(records):
    latest = max(r.period for r in records)
    thinned = [r for r in records
               if not (r.period == latest and r.breakdown == "total")]
    with pytest.raises(ValueError, match="전체"):
        ei.check_coverage(thinned)


def _shift(period: str, months: int) -> str:
    year, month = (int(x) for x in period.split("-"))
    total = year * 12 + (month - 1) - months
    return f"{total // 12}-{total % 12 + 1:02d}"


def test_freshness_check_fails_when_the_series_is_truncated(records):
    from datetime import date as _date
    # 파싱이 조용히 잘리면 check_coverage 는 못 잡는다 — 여기서 잡아야 한다.
    latest = max(r.period for r in records)
    year, month = (int(x) for x in latest.split("-"))
    cutoff = _shift(latest, ei.MAX_MONTHS_BEHIND + 1)
    truncated = [r for r in records if r.period <= cutoff]
    with pytest.raises(ValueError, match="뒤처졌다"):
        ei.check_freshness(truncated, _date(year, month, 28))


def test_freshness_check_passes_on_a_current_series(records):
    from datetime import date as _date
    latest = max(r.period for r in records)
    year, month = (int(x) for x in latest.split("-"))
    ei.check_freshness(records, _date(year, month, 28))


def test_parse_fails_loudly_when_the_summary_disagrees(data, monkeypatch):
    # 서식이 바뀌어 표를 잘못 읽으면 조용히 틀린 숫자를 넣지 말고 실패해야 한다
    monkeypatch.setattr(ei, "headline_delta", lambda tables: 999.0)
    with pytest.raises(ValueError, match="대조"):
        ei.parse(data, released_at=date(2026, 8, 11),
                 release_url="https://x/view", attachments=[],
                 collected_at=datetime(2026, 8, 30, 9, 0))


def test_parse_fails_when_the_summary_cannot_be_read(data, monkeypatch):
    # 요약문을 못 읽는 것이 곧 '서식이 바뀌었다' 는 신호다. 건너뛰면 가드가
    # 정작 위험할 때만 침묵한다.
    monkeypatch.setattr(ei, "headline_delta", lambda tables: None)
    with pytest.raises(ValueError, match="읽지 못했다"):
        ei.parse(data, released_at=date(2026, 8, 11),
                 release_url="https://x/view", attachments=[],
                 collected_at=datetime(2026, 8, 30, 9, 0))


def test_demo_tables_are_level_and_delta_not_rate(data):
    level, delta = ei.find_demo_tables(hwpx.tables(data))
    assert level[-1][1] == "15,877"
    assert delta[-1][1] == "277"


def test_demo_total_matches_the_industry_total(records):
    latest = max(r.period for r in records)
    total = next(r for r in records if r.period == latest and r.breakdown == "total")
    for breakdown in ("sex", "age"):
        parts = [r for r in records if r.period == latest and r.breakdown == breakdown]
        assert parts, f"{latest} {breakdown} 레코드가 없다"
        # 천명 단위로 반올림된 값이라 합이 총계와 정확히 같지 않다
        # (실측: 2026-07 증감 합 278 vs 전산업 277). 부분집합 열이 섞이면
        # 편차가 백 단위로 벌어지므로 1.5 로도 충분히 갈린다.
        assert abs(sum(p.value for p in parts) - total.value) <= 1.5
        assert abs(sum(p.yoy for p in parts) - total.yoy) <= 1.5


def test_collects_five_age_bands_and_two_sexes(records):
    latest = max(r.period for r in records)
    sex = {r.category: r for r in records if r.period == latest and r.breakdown == "sex"}
    age = {r.category: r for r in records if r.period == latest and r.breakdown == "age"}
    assert set(sex) == {"M", "F"}
    assert set(age) == {"15-29", "30-39", "40-49", "50-59", "60+"}
    assert sex["F"].value == 7205.0
    assert age["60+"].yoy == 209.0


def test_demo_series_covers_every_month_not_just_the_latest(records):
    periods = {r.period for r in records if r.breakdown == "age"}
    assert "2024-07" in periods and "2026-07" in periods
    assert len(periods) >= 24


def test_headline_delta_tolerates_spacing_and_particles():
    # 문구가 조금 달라진 것만으로 수집이 멈추면 안 된다.
    make = lambda s: [[[s]]]
    for text in [
        "○ ‘26.7월 고용보험 가입자는 27만 7천명 증가",
        "○ ‘26.7월 고용보험 가입자는 27만 7천 명 증가",
        "○ ‘26.7월 고용보험 가입자는 27만 7천명이 증가",
    ]:
        assert ei.headline_delta(make(text)) == pytest.approx(277.0)
