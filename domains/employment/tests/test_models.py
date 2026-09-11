from datetime import date, datetime

import pytest
from pydantic import ValidationError

from domains.employment.pipeline.models import Attachment, SeriesRecord, make_id


def rec(**over):
    base = dict(
        id="ei-2026-07-headcount-total",
        source="ei", series="headcount", breakdown="total", category=None,
        period="2026-07", value=15877.0, unit="천명", yoy=277.0, status="잠정",
        released_at=date(2026, 8, 11),
        release_url="https://www.moel.go.kr/news/enews/report/enewsView.do?news_seq=19759",
        attachments=[], collected_at=datetime(2026, 8, 30, 9, 0),
    )
    base.update(over)
    return SeriesRecord(**base)


def test_accepts_a_total_record():
    assert rec().breakdown == "total"


def test_industry_record_requires_a_category():
    with pytest.raises(ValidationError):
        rec(breakdown="industry", category=None)


def test_total_record_rejects_a_category():
    with pytest.raises(ValidationError):
        rec(breakdown="total", category="C")


def test_period_must_be_year_month():
    with pytest.raises(ValidationError):
        rec(period="2026-7")


def test_release_url_must_be_http():
    with pytest.raises(ValidationError):
        rec(release_url="javascript:alert(1)")


def test_attachments_carry_type_and_url():
    r = rec(attachments=[Attachment(type="hwpx", url="https://x/a.hwpx")])
    assert r.attachments[0].type == "hwpx"


def test_make_id_includes_category_only_for_industry():
    assert make_id("eaps", "2026-07", "total", None) == "eaps-2026-07-headcount-total"
    assert make_id("eaps", "2026-07", "industry", "C") == "eaps-2026-07-headcount-industry-C"


def test_make_id_carries_category_for_every_breakdown_but_total():
    assert make_id("eaps", "2026-07", "total", None) == "eaps-2026-07-headcount-total"
    assert make_id("eaps", "2026-07", "industry", "A") == "eaps-2026-07-headcount-industry-A"
    assert make_id("eaps", "2026-07", "sex", "M") == "eaps-2026-07-headcount-sex-M"
    assert make_id("ei", "2026-07", "age", "60+") == "ei-2026-07-headcount-age-60+"


def test_sex_and_age_records_need_a_category():
    def build(**over):
        base = dict(
            id="x", source="eaps", breakdown="sex", category="M", period="2026-07",
            value=16079.5, released_at=date(2026, 8, 12),
            release_url="https://mods.go.kr/x", collected_at=datetime(2026, 8, 30, 9, 0),
        )
        return SeriesRecord(**{**base, **over})

    build()                       # 정상
    build(breakdown="age", category="15-29")
    with pytest.raises(ValidationError):
        build(category=None)
    with pytest.raises(ValidationError):
        build(breakdown="age", category=None)


# ── 지표 축 ──────────────────────────────────────────────────────────

def test_make_id_separates_indicators():
    """지표가 id 에 들어가야 한다.

    안 들어가면 고용률과 취업자수가 같은 키를 갖고, store.upsert 가 둘을 같은
    관측으로 보고 서로 덮어쓴다 — 값이 조용히 뒤바뀐다.
    """
    assert (make_id("eaps", "2026-08", "total", None, series="employment_rate")
            != make_id("eaps", "2026-08", "total", None, series="headcount"))
    assert (make_id("eaps", "2026-08", "total", None, series="employment_rate")
            == "eaps-2026-08-employment_rate-total")


def test_make_id_keeps_every_existing_id_unchanged():
    """지표를 안 주면 예전 그대로다. 2,300여 건의 id 가 한 글자도 안 바뀐다."""
    assert make_id("eaps", "2026-07", "total", None) == "eaps-2026-07-headcount-total"
    assert make_id("ei", "2026-07", "age", "60+") == "ei-2026-07-headcount-age-60+"


def test_scope_records_carry_the_age_range_as_a_category():
    # 15~64세는 연령 구간들을 가로지른다. 연령 속성에 넣으면 속성별 매트릭스에서
    # 이중 계상으로 읽히므로 별도 축(scope)에 둔다.
    r = rec(breakdown="scope", category="15-64", series="employment_rate",
            unit="%", value=70.4, yoy=0.5,
            id=make_id("eaps", "2026-08", "scope", "15-64", series="employment_rate"))
    assert r.breakdown == "scope" and r.category == "15-64"
    assert r.id == "eaps-2026-08-employment_rate-scope-15-64"


def test_scope_records_need_a_category():
    with pytest.raises(ValidationError):
        rec(breakdown="scope", category=None)


def test_rate_records_are_measured_in_percent():
    assert rec(series="unemployment_rate", unit="%", value=2.0, yoy=0.0).unit == "%"


def test_an_unknown_indicator_is_refused():
    # 오타가 조용히 새 계열을 만들면 화면이 그 계열을 영영 못 찾는다.
    with pytest.raises(ValidationError):
        rec(series="emploment_rate")
