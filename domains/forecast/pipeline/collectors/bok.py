"""한국은행 경제전망보고서 수집기.

목록 페이지는 자바스크립트로 그려져 긁을 수 없으나, 같은 게시판의 RSS가
회차 제목·발표일시·본문 링크를 그대로 준다. 거기서 최신 회차를 찾아
본문에 붙은 PDF를 받고 요약표 페이지를 읽는다.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import NamedTuple

from .. import http, pdf
from ..models import ForecastRecord, INDICATOR_META, make_id

KST = timezone(timedelta(hours=9))

BASE = "https://www.bok.or.kr"
RSS_URL = f"{BASE}/portal/bbs/P0002359/news.rss?menuNo=200066"
LANDING_URL = f"{BASE}/portal/singl/newsData/list.do?menuNo=200066"

# 요약표로 인정하는 최소 지표. 앞쪽에 실린 부분 표(성장률·물가만 있는 표 등)를 거른다
REQUIRED_INDICATORS = {"gdp_growth", "cpi", "emp_change", "unemp_rate"}

# 요약표 행 이름(공백·단위·각주 제거) → 내부 지표코드
LABEL_TO_INDICATOR = {
    "GDP성장률": "gdp_growth",
    "소비자물가상승률": "cpi",
    "취업자수증감": "emp_change",
    "실업률": "unemp_rate",
    "고용률": "emp_rate",
}

_ITEM = re.compile(r"<item>(.*?)</item>", re.S)
_ISSUE_TITLE = re.compile(r"경제전망보고서\(\s*\d{4}년\s*\d{1,2}월\s*\)")
_PDF_HREF = re.compile(r'href="(/fileSrc/[^"]+\.pdf)"')


class Issue(NamedTuple):
    title: str
    published_at: date
    url: str


def _tag(item: str, name: str) -> str:
    match = re.search(rf"<{name}>(.*?)</{name}>", item, re.S)
    if not match:
        return ""
    value = match.group(1).strip()
    cdata = re.fullmatch(r"<!\[CDATA\[(.*?)\]\]>", value, re.S)
    return (cdata.group(1) if cdata else value).strip()


def parse_rss(xml: str) -> list[Issue]:
    """회차 항목만 최신순으로 돌려준다(발표시점 변경 안내 등 공지는 버린다)."""
    issues = []
    for raw in _ITEM.findall(xml):
        title = _tag(raw, "title")
        if not _ISSUE_TITLE.fullmatch(title):
            continue
        issues.append(Issue(
            title=title,
            published_at=parsedate_to_datetime(_tag(raw, "pubDate")).date(),
            url=_tag(raw, "link"),
        ))
    return sorted(issues, key=lambda i: i.published_at, reverse=True)


def parse_pdf_link(html: str) -> str:
    match = _PDF_HREF.search(html)
    if not match:
        raise ValueError("본문에서 PDF 첨부를 찾지 못했다")
    return BASE + match.group(1)


def parse(text: str, issue: Issue, source_url: str, source_page: int) -> list[ForecastRecord]:
    values = pdf.parse_summary_table(text, LABEL_TO_INDICATOR)
    collected_at = datetime.now(KST)
    records = []
    for (indicator, year, period), value in sorted(values.items()):
        # 발표연도보다 앞선 해는 전망이 아니라 실적이다
        if year < issue.published_at.year:
            continue
        meta = INDICATOR_META[indicator]
        records.append(ForecastRecord(
            id=make_id("BOK", issue.published_at, indicator, year, period),
            org="BOK",
            org_name_ko="한국은행",
            report_title=issue.title,
            published_at=issue.published_at,
            target_year=year,
            target_period=period,
            indicator=indicator,
            value=round(value, meta["decimals"]),
            unit=meta["unit"],
            source_url=source_url,
            source_page=source_page,
            landing_url=issue.url,
            confidence="extracted",
            collected_at=collected_at,
        ))
    return records




def collect(today: date) -> list[ForecastRecord]:
    issues = parse_rss(http.get(RSS_URL).text)
    if not issues:
        raise ValueError("RSS에서 경제전망보고서 회차를 찾지 못했다")
    issue = issues[0]
    pdf_url = parse_pdf_link(http.get(issue.url).text)
    found = pdf.find_summary_table(
        pdf.page_texts(http.get(pdf_url).content), LABEL_TO_INDICATOR, REQUIRED_INDICATORS
    )
    if found is None:
        raise ValueError(f"{issue.title}: 요약표 페이지를 찾지 못했다")
    page_no, text = found
    return parse(text, issue, pdf_url, page_no)
