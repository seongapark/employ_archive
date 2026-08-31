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
