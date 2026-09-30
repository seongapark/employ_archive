"""발표됐는데 없는 회차를 찾는다 — 수집기와 따로 선 감시.

수집 판정(check_run)은 "돌아간 수집기가 성공했나" 만 본다. 매일 수집에 없는
수집기, 성공하면서 새 회차를 못 보는 수집기(목록 주소·보고서 이름이 바뀐 경우)는
못 본다. 2026-09-23 OECD 9월 중간전망이 일주일 빠졌는데 매일 "8기관 전부 ok" 였다.
그래서 수집기가 아닌 곳에서 "나왔어야 할 회차" 를 따로 세운다.

1. OECD·IMF: 기획재정부가 두 기관 전망이 나오는 날 같은 날짜로 [보도참고]를 낸다
   (이미 쌓인 회차 날짜와 전부 일치 — oecd.EDITIONS 주석). 그 날짜가 우리 최신
   회차보다 새로운데 GRACE_DAYS 가 지나도록 없으면 실패다.
2. 국내 기관: 최근 발표 간격의 최댓값에 SLACK_DAYS 를 더한 만큼 새 회차가 없으면
   실패다. 달력을 손으로 적지 않는다 — 적어 둔 달력은 이번 사고의 EDITIONS 처럼
   아무도 안 고친다.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Callable, Iterable

from .models import ForecastRecord

GRACE_DAYS = 2
# ponytail: 간격 규칙은 한 주기가 통째로 빠져야 울린다(BOK 는 약 110일 뒤).
# 발표일이 미리 공지되는 기관은 1번처럼 공지와 대조하는 쪽으로 옮기면 빨라진다.
SLACK_DAYS = 21
RECENT_GAPS = 4

# 기재부 게시판 검색어 → 우리 기관 코드
NOTICE_KEYWORDS = {"경제협력개발기구": "OECD", "국제통화기금": "IMF"}
# 전망 발표 보도참고만. 한국경제보고서·연례협의·부채 동향은 전망 회차가 아니다.
_FORECAST_NOTICE = re.compile(r"^\[보도참고\].*경제전망")

Notice = tuple[str, date, str]  # (기관, 날짜, 제목)


def moef_notices(pages: int = 1) -> list[Notice]:
    """매일은 1쪽(약 1년치)이면 된다. 백필은 더 넘긴다."""
    from .collectors import moef
    from . import http

    notices = []
    for keyword, org in NOTICE_KEYWORDS.items():
        for page_no in range(1, pages + 1):
            rows = moef.parse_list(http.get(moef.LIST_URL.format(keyword=keyword, page=page_no)).text)
            if not rows:
                if page_no == 1:
                    raise ValueError(f"기재부 보도참고 목록이 비었다({keyword}) — 게시판 구조를 확인할 것")
                break
            notices.extend((org, published, title) for _, published, title in rows)
    return notices


def _latest(records: Iterable[ForecastRecord]) -> dict[str, date]:
    latest: dict[str, date] = {}
    for r in records:
        latest[r.org] = max(latest.get(r.org, r.published_at), r.published_at)
    return latest


def missing_announced(records: list[ForecastRecord], notices: list[Notice],
                      today: date) -> list[str]:
    latest = _latest(records)
    out = []
    for org, published, title in notices:
        if not _FORECAST_NOTICE.search(title):
            continue
        if published > latest.get(org, date.min) and today - published > timedelta(days=GRACE_DAYS):
            out.append(f"{org} {published} 회차가 없다 — 기재부 보도참고 「{title}」")
    return out


def overdue(records: list[ForecastRecord], today: date,
            orgs: Iterable[str]) -> list[str]:
    by_org: dict[str, set[date]] = {}
    for r in records:
        by_org.setdefault(r.org, set()).add(r.published_at)
    out = []
    for org in orgs:
        days = sorted(by_org.get(org, ()))
        if len(days) < 2:
            continue
        gaps = [(b - a).days for a, b in zip(days, days[1:])][-RECENT_GAPS:]
        limit = max(gaps) + SLACK_DAYS
        if (today - days[-1]).days > limit:
            out.append(f"{org} 새 회차가 {(today - days[-1]).days}일째 없다 "
                       f"(마지막 {days[-1]}, 최근 간격 최대 {max(gaps)}일)")
    return out


def check(records: list[ForecastRecord], today: date,
          notices: Callable[[], list[Notice]] = moef_notices) -> list[str]:
    announced = set(NOTICE_KEYWORDS.values())
    domestic = sorted({r.org for r in records} - announced)
    return missing_announced(records, notices(), today) + overdue(records, today, domestic)
