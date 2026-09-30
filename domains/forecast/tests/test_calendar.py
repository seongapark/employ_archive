from datetime import date, datetime

from domains.forecast.pipeline import calendar
from domains.forecast.pipeline.calendar import KST
from domains.forecast.tests.test_watch import rec


def at(y, m, d, h):
    return datetime(y, m, d, h, tzinfo=KST)


OECD = [rec("OECD", date(*d)) for d in
        [(2024, 12, 4), (2025, 3, 17), (2025, 6, 3), (2025, 9, 23),
         (2025, 12, 2), (2026, 3, 26), (2026, 6, 3)]]


def test_window_comes_from_the_same_month_in_history():
    # 9월 중간전망은 지난해 9/23 → 올해 9/20~9/26 을 본다
    assert calendar.next_window(OECD, "OECD", date(2026, 9, 1)) == (date(2026, 9, 20), date(2026, 9, 26))


def test_release_day_after_release_hour_is_due():
    # 2026-09-30 사고의 날: OECD 는 17시(10:00 CEST)에 낸다
    assert calendar.due(OECD, [], at(2026, 9, 23, 17)) == ["OECD"]
    assert calendar.due(OECD, [], at(2026, 9, 23, 11)) == []


def test_window_is_checked_every_three_hours_not_every_hour():
    # 발표일이 확정되지 않은 구간은 게시판 예의로 성기게 본다
    due_hours = [h for h in range(24) if calendar.due(OECD, [], at(2026, 9, 21, h))]
    assert due_hours == [17, 18, 20, 23]


def test_nothing_is_due_once_the_round_is_in():
    records = OECD + [rec("OECD", date(2026, 9, 23))]
    assert calendar.due(records, [], at(2026, 9, 24, 17)) == []


def test_months_older_than_two_years_do_not_make_windows():
    # EO 115 는 2024년 5월에 한 번 나왔다 — 해마다 5월을 보면 헛걸음이다
    records = OECD + [rec("OECD", date(2024, 5, 2))]
    assert calendar.due(records, [], at(2026, 5, 2, 17)) == []


def test_announced_date_is_checked_every_hour_from_release_hour():
    schedule = [{"org": "BOK", "date": "2026-11-26"}]
    bok = [rec("BOK", date(2026, 8, 27))]
    hours = [h for h in range(24) if calendar.due(bok, schedule, at(2026, 11, 26, h))]
    assert hours == list(range(10, 24))


def test_announced_date_already_collected_is_not_due():
    schedule = [{"org": "BOK", "date": "2026-11-26"}]
    bok = [rec("BOK", date(2026, 11, 26))]
    assert calendar.due(bok, schedule, at(2026, 11, 26, 15)) == []


def test_imf_is_due_late_at_night():
    imf = [rec("IMF", date(*d)) for d in [(2025, 10, 14), (2026, 1, 19), (2026, 4, 14), (2026, 7, 8)]]
    assert calendar.due(imf, [], at(2026, 10, 14, 22)) == ["IMF"]
    assert calendar.due(imf, [], at(2026, 10, 14, 12)) == []


def test_collectors_for_orgs():
    assert calendar.collectors_for(["OECD", "BOK"]) == ["oecd", "oecd_interim", "bok"]
    assert calendar.collectors_for(["IMF"]) == ["imf", "imf_update"]
