"""한국은행 경제전망보고서 수집기.

목록 페이지는 자바스크립트로 그려져 긁을 수 없으나, 같은 게시판의 RSS가
회차 제목·발표일시·본문 링크를 그대로 준다. 거기서 최신 회차를 찾아
본문에 붙은 PDF를 받고 요약표 페이지를 읽는다.
"""
from __future__ import annotations

import re
from datetime import date
from email.utils import parsedate_to_datetime

from .. import http, pdf, rationale_store, report
from ..models import ForecastRecord
from ..report import Issue  # 두 수집기가 같은 회차 표현을 쓴다

BASE = "https://www.bok.or.kr"
RSS_URL = f"{BASE}/portal/bbs/P0002359/news.rss?menuNo=200066"

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
    return report.records_from_table(
        text, LABEL_TO_INDICATOR,
        org="BOK", org_name_ko="한국은행",
        issue=issue, source_url=source_url, source_page=source_page,
    )


def list_issues() -> list[Issue]:
    """게시판에 남아 있는 회차를 최신순으로 준다(2014년까지 남는다)."""
    issues = parse_rss(http.get(RSS_URL).text)
    if not issues:
        raise ValueError("RSS에서 경제전망보고서 회차를 찾지 못했다")
    return issues


def collect_issue(issue: Issue) -> list[ForecastRecord]:
    """회차 하나의 본문에서 PDF를 받아 요약표를 읽는다."""
    pdf_url = parse_pdf_link(http.get(issue.url).text)
    found = pdf.find_summary_table(
        pdf.page_texts(http.get(pdf_url).content), LABEL_TO_INDICATOR, REQUIRED_INDICATORS
    )
    if found is None:
        raise ValueError(f"{issue.title}: 요약표 페이지를 찾지 못했다")
    page_no, text = found
    return parse(text, issue, pdf_url, page_no)


def collect_issue_rationales(issue: Issue) -> list["Rationale"]:
    """그 회차의 근거 문장을 준다. 요약표를 찾지 못하면 빈 리스트.

    표 앞뒤 한 쪽씩(page_no-1, page_no+1)을 표 쪽과 합쳐 넘긴다 —
    keis.collect_issue_rationales 와 같은 이유다: 서술이 표 앞과 뒤 중
    어디에 오는지 회차마다 다르다.

    이 창을 표 쪽 근처로만 좁혀 둔 것은 실측 때문이다. 2026년 8월호(69쪽
    짜리 PDF, 표는 16쪽)를 통째로 스캔해 보면 진짜 근거 문장은 8·10·11·
    39·43쪽처럼 표에서 멀리 떨어진 곳에 흩어져 있다(예: 39쪽 "올해
    취업자수 전망치는 … 지난 5월 전망 대비 4만명 하향조정하였다"). 반면
    그 통째 스캔은 위험하다 — 같은 호 3쪽(부문별 담당자 목록)이 "물가
    연구팀"·"고용동향팀"(지표 낱말)과 "…흐름과 배경"(인과 표지 — 사실은
    BOX 제목의 일부일 뿐이다)과 "향후 전망"(전망 표지)을 우연히 모두
    갖춰, rationale.pick 이 241자짜리 집필진 명단을 하나의 "근거 문장"
    으로 뽑아 버린다. 표 앞뒤 한 쪽으로 창을 좁히면 이 먼 쪽들은 놓치지만
    (실제 손실이다), 엉뚱한 문장을 이 기관의 근거인 양 인용하는 것보다는
    아무것도 인용하지 않는 편이 낫다 — 근거를 지어내지 않는다는 원칙과
    같은 이유다. 표 앞뒤 한 쪽(15·17쪽)은 실측으로 이 위험이 없음을
    확인했다: 둘 다 근거도 오탐도 없다.
    """
    pdf_url = parse_pdf_link(http.get(issue.url).text)
    pages = pdf.page_texts(http.get(pdf_url).content)
    found = pdf.find_summary_table(pages, LABEL_TO_INDICATOR, REQUIRED_INDICATORS)
    if found is None:
        return []
    page_no, _ = found

    collected: list["Rationale"] = []
    for neighbor in (page_no - 1, page_no, page_no + 1):
        if not (1 <= neighbor <= len(pages)):
            continue
        collected = rationale_store.merge(collected, report.rationales_from_text(
            pages[neighbor - 1], org="BOK", issue=issue,
            indicators=sorted(REQUIRED_INDICATORS), source_url=pdf_url,
            source_page=neighbor))
    return collected


def collect(today: date) -> list[ForecastRecord]:
    return collect_issue(list_issues()[0])
