import json
from datetime import date, datetime

import pytest

from domains.forecast.pipeline import backfill, store
from domains.forecast.pipeline.models import ForecastRecord, make_id


def rec(pub: date, value: float, org="BOK", indicator="gdp_growth", year=2026):
    return ForecastRecord(
        id=make_id(org, pub, indicator, year), org=org, org_name_ko=org,
        report_title="t", published_at=pub, target_year=year,
        indicator=indicator, value=value, unit="%",
        source_url="https://example.com/a", landing_url="https://example.com",
        confidence="extracted", collected_at=datetime(2026, 8, 30, 16, 0),
    )


def rounds(*specs):
    """(라벨, 발표일, 결과 또는 예외) 들로 이뤄진 가짜 회차 목록을 만든다."""
    out = []
    for label, pub, result in specs:
        def fetch(result=result):
            if isinstance(result, Exception):
                raise result
            return result
        out.append(backfill.Round(label=label, published_at=pub, fetch=fetch))
    return out


def test_collects_every_round_at_or_after_the_cutoff(tmp_path):
    src = {"bok": lambda: rounds(
        ("2026년 8월", date(2026, 8, 27), [rec(date(2026, 8, 27), 3.3)]),
        ("2026년 5월", date(2026, 5, 28), [rec(date(2026, 5, 28), 2.5)]),
    )}
    report = backfill.run(src, data_dir=tmp_path, since=date(2024, 11, 1))
    saved = store.load_forecasts(tmp_path / "forecasts.json")
    assert len(saved) == 2
    assert report.saved == 2 and report.failed == 0


def test_skips_rounds_published_before_the_cutoff(tmp_path):
    src = {"bok": lambda: rounds(
        ("2026년 8월", date(2026, 8, 27), [rec(date(2026, 8, 27), 3.3)]),
        ("2024년 8월", date(2024, 8, 28), [rec(date(2024, 8, 28), 1.0)]),
    )}
    report = backfill.run(src, data_dir=tmp_path, since=date(2024, 11, 1))
    assert {r.published_at for r in store.load_forecasts(tmp_path / "forecasts.json")} == {date(2026, 8, 27)}
    assert report.attempted == 1


def test_one_failing_round_does_not_stop_the_others(tmp_path):
    src = {"bok": lambda: rounds(
        ("2026년 8월", date(2026, 8, 27), [rec(date(2026, 8, 27), 3.3)]),
        ("2025년 11월", date(2025, 11, 27), ValueError("표 헤더 불일치")),
        ("2025년 8월", date(2025, 8, 28), [rec(date(2025, 8, 28), 1.8)]),
    )}
    report = backfill.run(src, data_dir=tmp_path, since=date(2024, 11, 1))
    assert len(store.load_forecasts(tmp_path / "forecasts.json")) == 2
    assert report.failed == 1
    assert report.failures == [("bok", "2025년 11월", "ValueError: 표 헤더 불일치")]


def test_a_source_that_cannot_be_listed_is_reported_not_raised(tmp_path):
    def boom():
        raise ConnectionError("HTTP Error 502: Bad Gateway")

    report = backfill.run({"kdi": boom}, data_dir=tmp_path, since=date(2024, 11, 1))
    assert report.failures == [("kdi", "회차 목록", "ConnectionError: HTTP Error 502: Bad Gateway")]


def test_revisions_are_recomputed_after_every_round_lands(tmp_path):
    # 8월호를 먼저 저장해 두고(수정폭 비어 있음) 5월호를 백필로 넣는다
    store.save_forecasts(tmp_path / "forecasts.json", [rec(date(2026, 8, 27), 3.3)])
    src = {"bok": lambda: rounds(("2026년 5월", date(2026, 5, 28), [rec(date(2026, 5, 28), 2.5)]))}
    backfill.run(src, data_dir=tmp_path, since=date(2024, 11, 1))
    saved = {r.published_at: r for r in store.load_forecasts(tmp_path / "forecasts.json")}
    assert saved[date(2026, 8, 27)].revision == 0.8
    assert saved[date(2026, 5, 28)].revision is None


def test_a_round_already_stored_is_skipped_not_duplicated(tmp_path):
    store.save_forecasts(tmp_path / "forecasts.json", [rec(date(2026, 8, 27), 3.3)])
    src = {"bok": lambda: rounds(("2026년 8월", date(2026, 8, 27), [rec(date(2026, 8, 27), 3.3)]))}
    report = backfill.run(src, data_dir=tmp_path, since=date(2024, 11, 1))
    assert len(store.load_forecasts(tmp_path / "forecasts.json")) == 1
    assert report.saved == 0


def test_only_the_named_sources_run(tmp_path):
    called = []
    src = {
        "bok": lambda: (called.append("bok") or rounds(("a", date(2026, 8, 27), [rec(date(2026, 8, 27), 3.3)]))),
        "oecd": lambda: (called.append("oecd") or []),
    }
    backfill.run(src, data_dir=tmp_path, since=date(2024, 11, 1), only=["oecd"])
    assert called == ["oecd"]


def test_bok_rounds_come_from_the_issue_list(monkeypatch):
    from domains.forecast.pipeline.collectors import bok
    monkeypatch.setattr(bok, "list_issues", lambda: [
        bok.Issue("경제전망보고서(2026년 8월)", date(2026, 8, 27), "u1"),
        bok.Issue("경제전망보고서(2026년 5월)", date(2026, 5, 28), "u2"),
    ])
    got = backfill.bok_rounds()
    assert [(r.label, r.published_at) for r in got] == [
        ("경제전망보고서(2026년 8월)", date(2026, 8, 27)),
        ("경제전망보고서(2026년 5월)", date(2026, 5, 28)),
    ]


def test_registered_sources_cover_the_backfillable_orgs():
    assert set(backfill.SOURCES) == {"oecd", "bok"}
