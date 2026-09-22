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
    # breakdown="total" 은 이제 아홉 계열이 같은 최신월을 공유한다 — series 로
    # 걸러야 상시가입자(headcount) 하나만 본다. 형제 테스트 셋(취득·상실 등)은
    # 이미 이 필터가 있는데 여기만 빠져 있었다.
    stated = ei.headline_delta(hwpx.tables(data))
    totals = [r for r in records if r.breakdown == "total" and r.series == "headcount"]
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
    # benefit_amount(구직급여 지급액)는 억원, openings_ratio(구인배수)는 배다 —
    # 둘 다 사람 머릿수가 아니라 돈·비율이라 단위가 다르다. 그 편은
    # test_the_payout_is_money_not_people·test_the_ratio_is_counted_in_multiples_not_in_people 가
    # 따로 본다.
    assert {r.unit for r in records
            if r.series not in ("benefit_amount", "openings_ratio")} == {"천명"}


def test_ids_are_unique(records):
    ids = [r.id for r in records]
    assert len(ids) == len(set(ids))


def test_reads_every_month_in_the_table_not_just_the_latest(records):
    # 표는 28개월치를 담고 있다. 마지막 행만 읽으면 24개월 시계열을 모으는 데
    # 2년이 걸린다.
    # breakdown="total" 은 이제 상시가입자뿐 아니라 취득·상실도 공유한다 —
    # series 로 걸러야 이 표(상시가입자) 하나만 본다.
    totals = [r for r in records if r.breakdown == "total" and r.series == "headcount"]
    periods = [r.period for r in totals]
    assert len(periods) == len(set(periods)), "같은 기간이 여러 번 나왔다"
    assert len(periods) >= 24
    assert max(periods) >= "2026-01"


def test_industry_sum_tracks_the_total(records):
    # 열이 밀리거나 집계 열('서비스업', '기타*')이 섞이면 합이 전체에서 벗어난다.
    # breakdown="industry" 는 이제 상시가입자(headcount)뿐 아니라 제조업 열
    # (benefit_new·benefit_paid·job_openings, category="C")도 공유한다 —
    # series 로 걸러야 상시가입자 19개 대분류의 합만 본다.
    latest = max(r.period for r in records)
    total = next(r.value for r in records
                 if r.breakdown == "total" and r.period == latest and r.series == "headcount")
    parts = sum(r.value for r in records
                if r.breakdown == "industry" and r.period == latest and r.series == "headcount")
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


def test_coverage_demands_every_indicator_in_the_latest_month(records):
    ei.check_coverage(records)      # 실물은 통과해야 한다
    thinned = [r for r in records if r.series != "benefit_amount"]
    with pytest.raises(ValueError, match="benefit_amount"):
        ei.check_coverage(thinned)


def test_coverage_demands_the_services_aggregate(records):
    thinned = [r for r in records
               if not (r.breakdown == "scope" and r.category == "services")]
    with pytest.raises(ValueError, match="서비스업"):
        ei.check_coverage(thinned)


def test_coverage_demands_the_manufacturing_columns(records):
    thinned = [r for r in records
               if not (r.breakdown == "industry" and r.category == "C"
                       and r.series == "job_openings")]
    with pytest.raises(ValueError, match="제조업"):
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


def test_parse_fails_when_the_age_columns_are_shifted(data, monkeypatch):
    # DEMO_COLUMNS 는 열 위치로 읽는다. 헤더 가드는 8개 라벨 중 5개만 요구하므로
    # 연령 블록 안에 열이 하나 끼어들어 30대→40대가 통째로 밀려도 통과한다.
    # 성별 두 열은 그대로라 성별 대조도 통과한다 — 연령 대조만이 이걸 잡는다.
    shifted = {2: ("sex", "M"), 3: ("sex", "F")}
    for col, key in ei.DEMO_COLUMNS.items():
        if key[0] == "age":
            shifted[col + 1] = key
    monkeypatch.setattr(ei, "DEMO_COLUMNS", shifted)
    with pytest.raises(ValueError, match="연령"):
        ei.parse(data, released_at=date(2026, 8, 11),
                 release_url="https://x/view", attachments=[],
                 collected_at=datetime(2026, 8, 30, 9, 0))


def test_parse_fails_when_the_sex_columns_are_shifted(data, monkeypatch):
    # 형제 가드. 성별이 밀리면 연령은 멀쩡하므로 성별 대조만이 잡는다.
    shifted = dict(ei.DEMO_COLUMNS)
    shifted[2] = ("sex", "M")
    shifted[3] = ("age", "15-29")   # 여자 열 자리에 연령이 밀려 들어온 모양
    monkeypatch.setattr(ei, "DEMO_COLUMNS", shifted)
    with pytest.raises(ValueError, match="성별"):
        ei.parse(data, released_at=date(2026, 8, 11),
                 release_url="https://x/view", attachments=[],
                 collected_at=datetime(2026, 8, 30, 9, 0))


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


# ── 총괄 지표: 취득·상실 ──────────────────────────────────────────────

def test_finds_the_flow_table_by_header_not_index(data):
    # 픽스처(2026-07)에서는 80번, 2026-08 회차에서는 81번이다. 표 번호가
    # 회차마다 밀리므로 인덱스로 집으면 다음 달에 조용히 다른 표를 읽는다.
    table = ei.find_flow_table(hwpx.tables(data))
    assert len(table) > 30
    assert "취득자수및상실자수" in " ".join(
        ei.squash(c) for c in table[0])


def test_acquisitions_split_into_new_and_experienced(data):
    # 문서 자체의 분해 항등식. 열이 하나라도 밀리면 계가 신규+경력과 어긋난다.
    ei.check_flow(ei.find_flow_table(hwpx.tables(data)))


def test_check_flow_fails_when_a_column_shifts(data, monkeypatch):
    table = ei.find_flow_table(hwpx.tables(data))
    # 신규 열 자리에서 상실자수를 읽는 모양으로 바꾼다.
    monkeypatch.setattr(ei, "FLOW_SPLIT", (("수준", 1, 4, 3), ("증감", 5, 6, 7)))
    with pytest.raises(ValueError, match="취득자수"):
        ei.check_flow(table)


def test_check_flow_fails_when_the_delta_block_shifts(data, monkeypatch):
    # 수준 블록(1,2,3)은 멀쩡한데 4번 열 뒤로 열 하나가 끼어들어 증감 블록만
    # 통째로 밀린 모양이다. 수준 항등식만 보면 이 사고를 놓친다.
    table = ei.find_flow_table(hwpx.tables(data))
    monkeypatch.setattr(ei, "FLOW_SPLIT", (("수준", 1, 2, 3), ("증감", 6, 7, 8)))
    with pytest.raises(ValueError, match="증감"):
        ei.check_flow(table)


def test_flow_records_carry_the_latest_month(data, records):
    latest = {(r.series, r.breakdown): r for r in records if r.period == "2026-07"}
    assert latest[("acquired", "total")].value == 660.0
    assert latest[("acquired", "total")].yoy == 33.0
    assert latest[("separated", "total")].value == 634.0
    assert latest[("separated", "total")].yoy == 23.0
    assert latest[("acquired", "total")].unit == "천명"


def test_flow_covers_every_month_not_just_the_latest(data, records):
    periods = {r.period for r in records if r.series == "acquired"}
    assert "2026-07" in periods
    assert len(periods) >= 25


# ── 총괄 지표: 구직급여 ────────────────────────────────────────────────

def test_finds_the_benefit_level_table_by_an_identity_not_by_size(data):
    # 헤더가 같은 표가 셋(수준·증감·증감률) 잇따른다. 지급액÷지급자수가
    # 1인당 지급액과 맞는 것은 수준 표뿐이다.
    level, delta = ei.find_benefit_tables(hwpx.tables(data))
    rows = dict(ei.month_rows(level))
    assert float(rows["2026-07"][4].replace(",", "")) == 10904.0
    assert float(dict(ei.month_rows(delta))["2026-07"][4].replace(",", "")) == -218.0


def test_benefit_records_carry_level_and_change(records):
    latest = {r.series: r for r in records
              if r.period == "2026-07" and r.breakdown == "total"}
    assert (latest["benefit_new"].value, latest["benefit_new"].yoy) == (109.0, -2.0)
    assert (latest["benefit_paid"].value, latest["benefit_paid"].yoy) == (643.0, -31.0)
    assert (latest["benefit_amount"].value, latest["benefit_amount"].yoy) == (10904.0, -218.0)


def test_the_payout_is_money_not_people(records):
    amount = next(r for r in records
                  if r.series == "benefit_amount" and r.period == "2026-07")
    assert amount.unit == "억원"
    paid = next(r for r in records
                if r.series == "benefit_paid" and r.period == "2026-07")
    assert paid.unit == "천명"


def test_is_benefit_level_rejects_the_change_and_rate_tables(data):
    # 증감률 표를 수준 표로 집으면 지급액이 100배 작아지는데 조용히 그럴듯해
    # 보인다. 크기로는 못 가르므로 항등식이 유일한 방패다.
    level, delta = ei.find_benefit_tables(hwpx.tables(data))
    assert ei._is_benefit_level(level) is True
    assert ei._is_benefit_level(delta) is False


def test_find_benefit_tables_fails_when_the_level_table_moves(data, monkeypatch):
    # 수준 표가 첫 장이 아니게 되면(표 순서가 바뀌면) 조용히 넘어가지 않는다.
    monkeypatch.setattr(ei, "_is_benefit_level", lambda table: False)
    with pytest.raises(ValueError, match="수준 표가 아니다"):
        ei.find_benefit_tables(hwpx.tables(data))


def _benefit_candidates(data):
    return [g for g in hwpx.tables(data)
            if g and len(g[0]) > 5 and all(k in ei._flat(g[0]) for k in ei.BENEFIT_HEADER_KEYS)]


def test_find_benefit_tables_fails_when_fewer_than_three_tables_are_found(data):
    # 수준·증감·증감률 셋이 다 있어야 순서를 항등식으로 못 박을 수 있다.
    # 둘만 찾히면 어느 게 증감이고 어느 게 증감률인지 가늠할 근거가 없다.
    cand = _benefit_candidates(data)
    with pytest.raises(ValueError, match="2개"):
        ei.find_benefit_tables(cand[:2])


def test_delta_matches_rate_on_the_real_fixture(data):
    # 세 번째 항등식: 증감 ÷ (수준 − 증감) × 100 ≈ 증감률. 문서의 실제 순서
    # (수준·증감·증감률)에서는 성립해야 한다.
    cand = _benefit_candidates(data)
    assert len(cand) >= 3
    assert ei._delta_matches_rate(cand[0], cand[1], cand[2]) is True


def test_delta_matches_rate_rejects_a_swapped_order(data):
    # 증감과 증감률 표의 자리가 바뀌면 항등식이 크게 어긋난다(브리프 실측:
    # 계산값이 218 어긋난다). 크기로는 못 가르는 자리를 이 식이 가른다.
    cand = _benefit_candidates(data)
    assert len(cand) >= 3
    assert ei._delta_matches_rate(cand[0], cand[2], cand[1]) is False


def test_find_benefit_tables_fails_when_delta_and_rate_are_swapped(data, monkeypatch):
    # 둘째·셋째 표의 자리가 바뀐 상황을 흉내낸다 — find_benefit_tables 가
    # 증감률을 증감으로 조용히 집지 않고 실패해야 한다.
    monkeypatch.setattr(ei, "_delta_matches_rate", lambda level, delta, rate: False)
    with pytest.raises(ValueError, match="순서"):
        ei.find_benefit_tables(hwpx.tables(data))


# ── 총괄 지표: 고용24 구인·구직 ─────────────────────────────────────────

def test_finds_the_market_level_table_by_the_ratio_identity(data):
    level, delta = ei.find_market_tables(hwpx.tables(data))
    assert ei._is_market_level(level) is True
    # 증감 표에서는 12.8 ÷ -11.5 가 0.04 가 될 수 없다.
    assert ei._is_market_level(delta) is False


def test_market_records_carry_level_and_change(records):
    latest = {r.series: r for r in records
              if r.period == "2026-07" and r.breakdown == "total"}
    assert (latest["job_openings"].value, latest["job_openings"].yoy) == (177.0, 12.8)
    assert (latest["job_seekers"].value, latest["job_seekers"].yoy) == (399.0, -11.5)
    assert (latest["openings_ratio"].value, latest["openings_ratio"].yoy) == (0.44, 0.04)


def test_the_ratio_is_counted_in_multiples_not_in_people(records):
    ratio = next(r for r in records
                 if r.series == "openings_ratio" and r.period == "2026-07")
    assert ratio.unit == "배"


def test_find_market_tables_fails_when_a_third_candidate_appears(data):
    # 고용24는 헤더가 같은 표가 수준·증감 둘뿐이다. 증감률 표까지 같은 헤더로
    # 새로 생기면 판별에 쓸 세 번째 항등식이 없다 — 추측 대신 개수로 막는다.
    # 그러지 않으면 cand[1]이 조용히 증감률이 되어 백분율이 yoy에 들어간다.
    cand = [g for g in hwpx.tables(data)
            if g and len(g[0]) >= 4 and all(k in ei._flat(g[0]) for k in ei.MARKET_HEADER_KEYS)]
    assert len(cand) == 2
    with pytest.raises(ValueError, match="3개"):
        ei.find_market_tables(cand + [cand[0]])


# ── 범위 탭: 제조업·서비스업 ───────────────────────────────────────────

def test_industry_pairs_are_matched_against_the_summary_totals(data):
    pairs = ei.industry_pairs(hwpx.tables(data))
    assert len(pairs) == 3          # 신규신청 · 지급자수 · 신규구인
    for level, delta in pairs:
        assert "전산업" in " ".join(ei.squash(c) for c in level[0])
        assert "전산업" in " ".join(ei.squash(c) for c in delta[0])


def test_manufacturing_columns_come_from_the_industry_tables(records):
    made = {r.series: r for r in records
            if r.period == "2026-07" and r.breakdown == "industry" and r.category == "C"}
    assert (made["benefit_new"].value, made["benefit_new"].yoy) == (16.0, -1.1)
    assert (made["benefit_paid"].value, made["benefit_paid"].yoy) == (110.0, -3.6)
    assert (made["job_openings"].value, made["job_openings"].yoy) == (56.0, 3.3)


def test_parse_fails_when_an_industry_table_disagrees_with_the_summary(data, monkeypatch):
    # 표 순서가 흔들려 지급자수 표를 신규신청 자리에서 읽으면, 전산업 값이
    # 요약표와 크게 어긋난다(109 vs 643).
    monkeypatch.setattr(ei, "INDUSTRY_SERIES",
                        ("benefit_paid", "benefit_new", "job_openings"))
    with pytest.raises(ValueError, match="전산업"):
        ei.parse(data, released_at=date(2026, 8, 11),
                 release_url="https://x/view", attachments=[],
                 collected_at=datetime(2026, 8, 30, 9, 0))


def test_manufacturing_records_fails_when_a_summary_total_is_missing(data):
    # 구직급여·고용24 요약표가 서로 다른 최신월을 낸 모양을 흉내낸다(한쪽
    # 표가 뒤처지면 totals 에 INDUSTRY_SERIES 세 지표 중 하나가 아예 빠진다).
    # 맥락 없는 KeyError 대신, 어느 지표가 빠졌는지 말하는 ValueError 여야 한다.
    tables = hwpx.tables(data)
    totals = {"benefit_new": (109.0, -2.0), "benefit_paid": (643.0, -31.0)}
    with pytest.raises(ValueError, match="job_openings"):
        ei.manufacturing_records(
            tables, totals, "2026-07",
            released_at=date(2026, 8, 11), release_url="https://x/view",
            attachments=[], collected_at=datetime(2026, 8, 30, 9, 0))


def test_services_is_an_aggregate_on_the_scope_axis_not_an_industry(records):
    services = [r for r in records if r.breakdown == "scope" and r.category == "services"]
    latest = max(services, key=lambda r: r.period)
    assert latest.period == "2026-07"
    assert latest.value == 11139.0
    assert latest.series == "headcount"
    # 대분류 목록은 그대로여야 한다 — 서비스업이 industry 로 새면 이중 계상이다.
    codes = {r.category for r in records if r.breakdown == "industry"
             and r.series == "headcount"}
    assert codes == set("ACDEFGHIJKLMNOPQRS")


# ── 세 회차 통째 검증 ────────────────────────────────────────────────────

RELEASES = Path(__file__).parents[3] / "domains" / "press" / "sources" / "releases"


def longest_consecutive_run(periods) -> int:
    # 그래프가 첫 수집만으로 가득 차려면 개수가 아니라 '끊기지 않은 구간'이
    # 필요하다 — 연도 경계가 잘못 밀리면 개수는 그대로인데 구간만 끊긴다.
    # 중복이 섞인 iterable 로 불리면 run 을 과소 계산한다 — 모든 호출부가
    # set 을 넘기는 지금은 죽은 위험이지만 set() 으로 한 토큰에 닫는다.
    months = sorted(set(periods))
    if not months:
        return 0
    best = run = 1
    for prev, cur in zip(months, months[1:]):
        py, pm = (int(x) for x in prev.split("-"))
        cy, cm = (int(x) for x in cur.split("-"))
        if (py * 12 + pm) + 1 == (cy * 12 + cm):
            run += 1
        else:
            run = 1
        best = max(best, run)
    return best


def test_longest_consecutive_run_ignores_scattered_months():
    scattered = {f"{2000 + i}-01" for i in range(25)}
    assert longest_consecutive_run(scattered) < 25
    consecutive = {_shift("2026-01", m) for m in range(25)}
    assert longest_consecutive_run(consecutive) == 25


@pytest.mark.parametrize("name", ["ei_2026-06", "ei_2026-07", "ei_2026-08"])
def test_every_stored_issue_parses_with_all_nine_indicators(name):
    # 한 회차만 통과하는 파서는 다음 달에 깨진다. 표 번호가 회차마다 밀리므로
    # 헤더로 찾는 것이 실제로 되는지는 여러 회차로만 확인된다.
    #
    # domains/press/sources/releases/ 는 정책상 gitignore(회차당 1.4MB, 게시판에서
    # 다시 받을 수 있음)라 CI 에서는 이 파일들이 없어 통째로 skip 된다. 그런데
    # 2026-07 회차의 바이트는 domains/employment/tests/fixtures/ 에 이미 추적되어
    # 있다(다른 테스트들이 쓰는 FIXTURE) — 굳이 gitignore 폴더에서 다시 찾을
    # 이유가 없다. 이 경우만 추적된 경로로 돌려 25개월 연속 구간 단언이
    # CI 에서도 실제로 실행되게 한다. 나머지 둘(06·08)은 다회차 보장용이라
    # 정책상 여전히 파일이 있을 때만 돈다.
    path = FIXTURE if name == "ei_2026-07" else RELEASES / f"{name}.hwpx"
    if not path.exists():
        pytest.skip(f"{name} 회차가 저장소에 없다")
    parsed = ei.parse(path.read_bytes(), released_at=date(2026, 9, 7),
                      release_url="https://x/view", attachments=[],
                      collected_at=datetime(2026, 9, 21, 9, 0))
    ei.check_coverage(parsed)
    latest = max(r.period for r in parsed)
    got = {r.series for r in parsed if r.period == latest and r.breakdown == "total"}
    assert got == set(ei.EXPECTED_SERIES)
    # 25개월 연속 구간이 다 차야 그래프가 첫 수집만으로 가득 찬다.
    for series in ei.EXPECTED_SERIES:
        periods = {r.period for r in parsed
                   if r.series == series and r.breakdown == "total"}
        run = longest_consecutive_run(periods)
        assert run >= 25, f"{series} 의 연속 구간이 {run}개월뿐이다"
