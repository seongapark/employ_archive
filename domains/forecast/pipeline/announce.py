"""기관이 미리 공지한 발표일을 schedule.json 에 채운다(매일 수집이 부른다).

공지일이 있으면 발표일 재수집(calendar.due)이 그날 발표 시각부터 매시간 본다.
없으면 지난 발표일로 잡은 예상 구간을 3시간마다 볼 뿐이다. 손으로 적던 파일이라
BOK 11/26 한 줄뿐이었다.

- BOK: 경제전망은 2·5·8·11월 금통위(통화정책방향 결정회의) 날 나온다. 2026년
  2·5·8월 회의일이 실제 발표일과 같다. 한 해치 일정이 한 페이지에 있다.
- OECD: 발표 1~2주 전 보도 안내를 낸다. 주소에 날짜가 들어 있다
  (`oecd-to-release-interim-economic-outlook-on-wednesday-23-september-2026`).
- IMF·국내 연구기관은 미리 공지하는 곳을 찾지 못했다 — 예상 구간과 감시(watch)가 맡는다.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from .calendar import PAD_DAYS

BOK_MEETINGS_URL = ("https://www.bok.or.kr/portal/singl/crncyPolicyDrcMtg/listYear.do"
                    "?mtgSe=A&menuNo=200755&pYear={year}")
BOK_OUTLOOK_MONTHS = (2, 5, 8, 11)
OECD_NEWS_URL = "https://www.oecd.org/en/about/news.html"

_BOK_ROW = re.compile(r'<th scope="row">\s*(\d{1,2})월\s*(\d{1,2})일')
_BOK_YEAR = re.compile(r'<option[^>]*selected[^>]*>\s*(\d{4})')
_OECD_ADVISORY = re.compile(
    r"/en/about/news/media-advisories/(?P<py>\d{4})/(?P<pm>\d{2})/"
    r"oecd-to-release-(?P<what>[a-z-]*economic-outlook)-on-(?:[a-z]+-)?"
    r"(?P<day>\d{1,2})-(?P<month>[a-z]+)(?:-(?P<year>\d{4}))?\.html")
_MONTHS = ("january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december")


def bok_meeting_days(page_html: str, year: int) -> list[date]:
    """그 해 경제전망이 나오는 금통위 날짜. 다른 해의 페이지면 빈 목록."""
    shown = _BOK_YEAR.search(page_html)
    if not shown or int(shown.group(1)) != year:
        return []
    days = [date(year, int(m), int(d)) for m, d in _BOK_ROW.findall(page_html)]
    return [d for d in days if d.month in BOK_OUTLOOK_MONTHS]


def oecd_outlook_days(page_html: str) -> list[tuple[date, str]]:
    out = set()
    for m in _OECD_ADVISORY.finditer(page_html):
        if m["month"] not in _MONTHS:
            continue
        month = _MONTHS.index(m["month"]) + 1
        # 연도가 없는 주소는 게시한 달로 정한다(12월에 1월 발표를 알리면 다음 해)
        year = int(m["year"] or int(m["py"]) + (month < int(m["pm"])))
        report = "Interim Economic Outlook" if "interim" in m["what"] else "Economic Outlook"
        out.add((date(year, month, int(m["day"])), report))
    return sorted(out)


def discover(today: date, fetch) -> list[dict]:
    found = []
    for year in (today.year, today.year + 1):
        days = bok_meeting_days(fetch(BOK_MEETINGS_URL.format(year=year)), year)
        if year == today.year and not days:
            # 올해 일정은 늘 있다 — 못 읽었으면 페이지가 바뀐 것이다(내년 것은 연말에야 나온다)
            raise ValueError("한국은행 금통위 일정에서 올해 경제전망 회의일을 찾지 못했다")
        found += [{"org": "BOK", "org_name_ko": "BOK", "report": "경제전망",
                   "date": day.isoformat()} for day in days]
    for day, report in oecd_outlook_days(fetch(OECD_NEWS_URL)):
        found.append({"org": "OECD", "org_name_ko": "OECD", "report": report,
                      "date": day.isoformat()})
    return found


def refresh(schedule_path, today: date, fetch) -> int:
    """schedule.json 을 갱신하고 새로 더한 공지일 수를 준다."""
    import json
    from pathlib import Path

    path = Path(schedule_path)
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    new = merge(old, discover(today, fetch), today)
    if new != old:
        path.write_text(json.dumps(new, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len({(e["org"], e["date"]) for e in new} - {(e["org"], e["date"]) for e in old})


def merge(schedule: list[dict], found: list[dict], today: date) -> list[dict]:
    """공지일을 더하고, 발표일 재수집이 더는 보지 않을 만큼 지난 날은 뺀다."""
    keep_from = (today - timedelta(days=PAD_DAYS)).isoformat()
    by_key = {(e["org"], e["date"]): e for e in schedule}
    for e in found:
        by_key.setdefault((e["org"], e["date"]), e)
    return sorted((e for e in by_key.values() if e["date"] >= keep_from),
                  key=lambda e: (e["date"], e["org"]))
