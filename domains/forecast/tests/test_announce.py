from datetime import date
from pathlib import Path

from domains.forecast.pipeline import announce

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_bok_outlook_days_are_the_policy_meetings_of_feb_may_aug_nov():
    # 2026년 2·5·8월 회의일(2/26·5/28·8/27)이 실제 경제전망 발표일과 같다
    assert announce.bok_meeting_days(load("bok_meetings_2026.html"), 2026) == [
        date(2026, 2, 26), date(2026, 5, 28), date(2026, 8, 27), date(2026, 11, 26)]


def test_bok_page_of_another_year_is_ignored():
    # 아직 안 나온 해를 물으면 올해 페이지가 돌아온다 — 올해 날짜를 내년 것으로 착각하면 안 된다
    assert announce.bok_meeting_days(load("bok_meetings_2026.html"), 2027) == []


def test_oecd_outlook_days_come_from_media_advisory_addresses():
    assert announce.oecd_outlook_days(load("oecd_news_links.html")) == [
        (date(2026, 9, 23), "Interim Economic Outlook")]


def test_oecd_advisory_without_year_takes_it_from_the_path():
    html = ('<a href="/en/about/news/media-advisories/2026/11/'
            'oecd-to-release-latest-economic-outlook-on-wednesday-2-december.html">')
    assert announce.oecd_outlook_days(html) == [(date(2026, 12, 2), "Economic Outlook")]
    html = html.replace("2026/11/", "2026/12/").replace("2-december", "5-january")
    assert announce.oecd_outlook_days(html) == [(date(2027, 1, 5), "Economic Outlook")]


def test_merge_adds_new_days_and_drops_stale_ones():
    schedule = [
        {"org": "BOK", "org_name_ko": "BOK", "report": "경제전망", "date": "2026-08-27"},
        {"org": "BOK", "org_name_ko": "BOK", "report": "경제전망", "date": "2026-11-26"},
    ]
    found = [{"org": "BOK", "org_name_ko": "BOK", "report": "경제전망", "date": "2026-11-26"},
             {"org": "OECD", "org_name_ko": "OECD", "report": "Economic Outlook", "date": "2026-12-02"}]
    got = announce.merge(schedule, found, date(2026, 9, 30))
    assert [(e["org"], e["date"]) for e in got] == [("BOK", "2026-11-26"), ("OECD", "2026-12-02")]


def test_merge_keeps_a_day_just_passed_while_it_may_still_be_collected():
    # 발표일 재수집(calendar.due)은 공지일 뒤 며칠까지 본다 — 그동안 지우면 안 된다
    schedule = [{"org": "OECD", "org_name_ko": "OECD", "report": "x", "date": "2026-09-23"}]
    assert announce.merge(schedule, [], date(2026, 9, 25)) == schedule
    assert announce.merge(schedule, [], date(2026, 9, 30)) == []
