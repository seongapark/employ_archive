from datetime import date, datetime
from domains.forecast.pipeline.models import ForecastRecord, make_id
from domains.forecast.pipeline import store


def rec(month: int, value: float, year: int = 2027, org: str = "OECD",
        indicator: str = "gdp_growth", day: int = 15) -> ForecastRecord:
    pub = date(2026, month, day)
    return ForecastRecord(
        id=make_id(org, pub, indicator, year), org=org, org_name_ko=org,
        report_title="test", published_at=pub, target_year=year,
        indicator=indicator, value=value, unit="%",
        source_url="https://example.com/a", landing_url="https://example.com",
        confidence="verified", collected_at=datetime(2026, month, 15, 16, 0),
    )


def test_first_insert_has_no_prev():
    result = store.merge([], [rec(6, 2.0)])
    assert result.added == ["oecd-2026-06-gdp_growth-2027"]
    assert result.records[0].prev_value is None
    assert result.records[0].revision is None


def test_second_edition_links_prev_and_revision():
    first = store.merge([], [rec(6, 2.0)]).records
    result = store.merge(first, [rec(8, 2.3)])
    added = [r for r in result.records if r.id == "oecd-2026-08-gdp_growth-2027"][0]
    assert added.prev_value == 2.0
    assert added.revision == 0.3


def test_same_id_same_value_skipped():
    first = store.merge([], [rec(6, 2.0)]).records
    result = store.merge(first, [rec(6, 2.0)])
    assert result.skipped == ["oecd-2026-06-gdp_growth-2027"]
    assert len(result.records) == 1


def test_same_id_different_value_is_reidentified_not_overwritten():
    # Per controller ruling, a same-month id collision with a different
    # value is an intra-month revision, not a conflict: it gets re-id'd
    # with day precision rather than discarded.
    first = store.merge([], [rec(6, 2.0)]).records
    result = store.merge(first, [rec(6, 2.5)])
    assert not result.conflicts
    assert result.records[0].value == 2.0  # 원본은 덮어쓰지 않음
    day_rec = [r for r in result.records if r.id == "oecd-2026-06-15-gdp_growth-2027"][0]
    assert day_rec.value == 2.5


def test_day_level_id_collision_with_different_value_is_conflict():
    first = store.merge([], [rec(6, 2.0, day=5)]).records
    after_revision = store.merge(first, [rec(6, 2.3, day=20)]).records
    # A second, conflicting candidate for the exact same day should not overwrite
    result = store.merge(after_revision, [rec(6, 2.9, day=20)])
    assert len(result.conflicts) == 1
    day_rec = [r for r in result.records if r.id == "oecd-2026-06-20-gdp_growth-2027"][0]
    assert day_rec.value == 2.3  # 덮어쓰지 않음


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "forecasts.json"
    records = store.merge([], [rec(6, 2.0), rec(8, 2.3)]).records
    store.save_forecasts(path, records)
    loaded = store.load_forecasts(path)
    assert [r.id for r in loaded] == [r.id for r in records]
    assert loaded[1].prev_value == 2.0


def test_load_missing_file_returns_empty(tmp_path):
    assert store.load_forecasts(tmp_path / "nope.json") == []


def test_backfill_out_of_order_links_to_immediate_predecessor():
    # Merge Jan(2.0) first
    after_jan = store.merge([], [rec(1, 2.0)]).records
    # Then merge Aug(2.5) which should have prev_value=2.0 from Jan
    after_aug = store.merge(after_jan, [rec(8, 2.5)]).records
    aug_rec = [r for r in after_aug if r.id == "oecd-2026-08-gdp_growth-2027"][0]
    assert aug_rec.prev_value == 2.0
    assert aug_rec.revision == 0.5

    # Now backfill June(2.3) which should link to Jan (immediate predecessor)
    result = store.merge(after_aug, [rec(6, 2.3)])
    june_rec = [r for r in result.records if r.id == "oecd-2026-06-gdp_growth-2027"][0]
    assert june_rec.prev_value == 2.0
    assert june_rec.revision == 0.3

    # Aug's record should remain unchanged
    aug_stored = [r for r in result.records if r.id == "oecd-2026-08-gdp_growth-2027"][0]
    assert aug_stored.prev_value == 2.0  # unchanged
    assert aug_stored.revision == 0.5  # unchanged


def test_intra_month_revision_captured_with_day_precision_id():
    # June 5th edition: 2.0
    first = store.merge([], [rec(6, 2.0, day=5)]).records
    # June 20th edition (same month, different value) should NOT be dropped
    result = store.merge(first, [rec(6, 2.3, day=20)])
    assert not result.conflicts
    day_rec = [r for r in result.records if r.id == "oecd-2026-06-20-gdp_growth-2027"][0]
    assert day_rec.prev_value == 2.0
    assert day_rec.revision == 0.3
    assert len(result.records) == 2


def test_intra_month_revision_reidentified_dup_is_skipped():
    first = store.merge([], [rec(6, 2.0, day=5)]).records
    after_revision = store.merge(first, [rec(6, 2.3, day=20)]).records
    assert len(after_revision) == 2
    # Merging the exact same June 20th candidate again should be a no-op skip
    result = store.merge(after_revision, [rec(6, 2.3, day=20)])
    assert len(result.records) == 2
    assert not result.conflicts
    day_ids = [r.id for r in result.records if r.id == "oecd-2026-06-20-gdp_growth-2027"]
    assert len(day_ids) == 1
