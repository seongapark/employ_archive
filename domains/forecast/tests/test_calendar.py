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


# ── 향후 6개월 일정표(upcoming.json) ───────────────────────────────────

def _rec(org, d, title="t"):
    r = rec(org, d)
    return r.model_copy(update={"report_title": title})


def test_upcoming_lists_every_expected_round_within_six_months():
    records = OECD + [rec("OECD", date(2026, 9, 23))]
    got = calendar.upcoming(records, [], date(2026, 10, 2))
    assert [(e["org"], e["start"], e["end"]) for e in got] == [
        ("OECD", "2026-11-29", "2026-12-07"), ("OECD", "2027-03-14", "2027-03-29")]
    assert [e["report"] for e in got] == ["경제전망", "중간 경제전망"]
    assert all(e["basis"] == "예상" and e["date"] is None for e in got)


def test_announced_date_marks_its_round():
    records = [rec("BOK", date(*d)) for d in [(2025, 11, 27), (2026, 2, 26), (2026, 5, 28), (2026, 8, 27)]]
    got = calendar.upcoming(records, [{"org": "BOK", "date": "2026-11-26"}], date(2026, 10, 2))
    nov = got[0]
    assert (nov["date"], nov["basis"], nov["report"]) == ("2026-11-26", "공지", "경제전망보고서")
    assert [e["start"][:7] for e in got] == ["2026-11", "2027-02"]


def test_a_round_already_in_is_not_listed():
    records = OECD + [rec("OECD", date(2026, 9, 23))]
    got = calendar.upcoming(records, [], date(2026, 9, 24))
    assert all(e["start"] > "2026-09-30" for e in got)


def test_adjacent_months_of_the_same_report_become_one_window():
    # 재정부 하반기 전략: 2025년엔 8/22, 2026년엔 7/14 — 같은 보고서가 달을 옮겼다
    records = [rec("MOEF", date(2025, 8, 22)), rec("MOEF", date(2026, 1, 9)), rec("MOEF", date(2026, 7, 14))]
    got = calendar.upcoming(records, [], date(2027, 3, 1), months=6)
    july = [e for e in got if e["report"] == "하반기 경제성장전략"]
    assert len(july) == 1 and (july[0]["start"], july[0]["end"]) == ("2027-07-11", "2027-08-25")


def test_unknown_month_falls_back_to_the_latest_title():
    records = [_rec("ZZZ", date(2025, 11, 3), "어느 보고서 2025"), _rec("ZZZ", date(2026, 11, 2), "어느 보고서 2026")]
    got = calendar.upcoming(records, [], date(2026, 12, 1), months=12)
    assert got[0]["report"] == "어느 보고서 2026"
