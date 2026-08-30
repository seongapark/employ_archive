import json
from datetime import date, datetime
from pathlib import Path

import pytest

from domains.employment.pipeline.collectors import est

FIXTURE = Path(__file__).parent / "fixtures" / "est_kosis.json"


@pytest.fixture(scope="module")
def records():
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return est.parse(
        rows,
        released_at=date(2026, 7, 29),
        release_url="https://kosis.kr/statHtml/statHtml.do?orgId=118&tblId=DT_118N_MON066",
        collected_at=datetime(2026, 8, 30, 9, 0),
    )


def test_major_code_regex_separates_divisions_from_subclasses():
    assert est.MAJOR_CODE_RE.search("260225INDUSTRY_11SD")
    assert not est.MAJOR_CODE_RE.search("260225INDUSTRY_11SD35")


def test_values_are_converted_to_thousands(records):
    totals = [r for r in records if r.breakdown == "total"]
    assert totals
    newest = max(totals, key=lambda r: r.period)
    # 종사자 2,070만명 -> 20,700 천명 언저리
    assert 19000 < newest.value < 22000
    assert newest.unit == "천명"


def test_industry_codes_match_what_the_survey_covers(records):
    codes = {r.category for r in records if r.breakdown == "industry"}
    assert codes == set("BCDEFGHIJKLMNOPQRS")
    # 사업체 조사라 농림어업·가구내고용·국제기관은 없다
    assert not ({"A", "T", "U"} & codes)


def test_subclasses_are_excluded(records):
    # 중분류가 섞이면 대분류가 이중 계상된다
    for r in records:
        assert r.category is None or len(r.category) == 1


def test_year_over_year_is_computed_from_twelve_months_earlier(records):
    manufacturing = sorted(
        (r for r in records if r.breakdown == "industry" and r.category == "C"),
        key=lambda r: r.period)
    assert len(manufacturing) >= 13
    by_period = {r.period: r for r in manufacturing}
    newest = manufacturing[-1]
    year, month = newest.period.split("-")
    prior = by_period.get(f"{int(year) - 1}-{month}")
    assert prior is not None
    assert newest.yoy == pytest.approx(round(newest.value - prior.value, 1))


def test_oldest_records_have_no_year_over_year(records):
    oldest = min(r.period for r in records)
    assert all(r.yoy is None for r in records if r.period == oldest)


def test_coverage_check_passes_on_a_complete_month(records):
    est.check_coverage(records)          # 예외가 나면 실패


def test_coverage_check_fails_loudly_when_an_industry_vanishes(records):
    # 코드 체계가 바뀌어 산업이 조용히 빠지면 화면에서 빈 칸으로만 보인다.
    latest = max(r.period for r in records)
    thinned = [r for r in records
               if not (r.period == latest and r.category == "C")]
    with pytest.raises(ValueError, match="빠진 산업"):
        est.check_coverage(thinned)
