from datetime import date, datetime

import pytest

from domains.employment.pipeline.models import SeriesRecord
from domains.employment.pipeline import store


def rec(period="2026-07", value=15877.0, yoy=277.0, released=date(2026, 8, 11),
        breakdown="total", category=None, source="ei"):
    from domains.employment.pipeline.models import make_id
    return SeriesRecord(
        id=make_id(source, period, breakdown, category),
        source=source, breakdown=breakdown, category=category, period=period,
        value=value, yoy=yoy, released_at=released,
        release_url="https://x/view?news_seq=1",
        collected_at=datetime(2026, 8, 30, 9, 0),
    )


def test_upsert_adds_new_records():
    r = store.upsert([], [rec()])
    assert r.added == ["ei-2026-07-headcount-total"]
    assert len(r.records) == 1


def test_upsert_leaves_identical_records_alone():
    first = [rec()]
    r = store.upsert(first, [rec()])
    assert r.unchanged == ["ei-2026-07-headcount-total"]
    assert r.added == [] and r.updated == []


def test_upsert_overwrites_a_revised_value():
    # 6월 수치가 7월 발표본에서 15855 -> 15856 으로 조정된 실제 사례
    old = [rec(period="2026-06", value=15855.0, released=date(2026, 7, 14))]
    new = [rec(period="2026-06", value=15856.0, released=date(2026, 8, 11))]
    r = store.upsert(old, new)
    assert r.updated == ["ei-2026-06-headcount-total"]
    assert len(r.records) == 1
    assert r.records[0].value == 15856.0
    assert r.records[0].released_at == date(2026, 8, 11)


def test_upsert_ignores_a_stale_release():
    # 더 오래된 발표본이 뒤늦게 들어와도 최신 수치를 덮지 않는다
    new_first = [rec(period="2026-06", value=15856.0, released=date(2026, 8, 11))]
    stale = [rec(period="2026-06", value=15855.0, released=date(2026, 7, 14))]
    r = store.upsert(new_first, stale)
    assert r.records[0].value == 15856.0
    assert r.updated == []


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "series.json"
    store.save_series(path, [rec(), rec(period="2026-06")])
    back = store.load_series(path)
    assert [b.id for b in back] == [
        "ei-2026-06-headcount-total", "ei-2026-07-headcount-total"
    ]


def test_load_returns_empty_when_the_file_is_missing(tmp_path):
    assert store.load_series(tmp_path / "nope.json") == []


def test_upsert_writes_to_the_right_slot_when_ids_repeat():
    # 값 비교로 자리를 찾으면 by_id 가 가리키는 뒤쪽이 아니라 앞쪽 중복을 덮는다.
    # 그래서 '어느 값이 어딘가에 있다'가 아니라 '어느 자리가 덮였다'를 봐야 한다.
    dup = rec(period="2026-06", value=15855.0, released=date(2026, 7, 14))
    other = rec(period="2026-07")
    twin = dup.model_copy()
    existing = [dup, other, twin]
    cand = rec(period="2026-06", value=15856.0, released=date(2026, 8, 11))

    r = store.upsert(existing, [cand])

    # by_id 는 뒤에 온 twin 을 가리키므로 덮여야 하는 것은 인덱스 2다.
    assert r.records[2] is cand
    # 앞쪽 중복은 손대지 않아야 한다 — 값 비교였다면 여기가 cand 로 바뀐다.
    assert r.records[0] is dup
    assert r.records[0].value == 15855.0
    assert r.updated == [cand.id]


def test_load_series_rejects_duplicate_ids(tmp_path):
    import json as _json
    path = tmp_path / "series.json"
    row = rec().model_dump(mode="json")
    path.write_text(_json.dumps([row, row], ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="중복"):
        store.load_series(path)
