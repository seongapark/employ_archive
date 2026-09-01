"""한국노동연구원 「노동시장 평가와 전망」 수집기.

노동리뷰 특집으로 연 2회(상반기 평가·연간 전망) 나온다. 게시판 목록에서 회차를
찾아 첨부 PDF 를 받고 <표 N> 고용 전망 표를 읽는다.

이 보고서는 노동시장만 다뤄 성장률·물가가 없다. 대신 취업자 증감·실업률·고용률을
반기까지 실어, 고용전망 아카이브에는 기관 중 가장 잘 맞는 자료다.
"""
from __future__ import annotations

import html as html_lib
import re
from datetime import date, datetime

from .. import http, pdf, report
from ..models import ForecastRecord
from ..report import Issue  # 회차 표현은 다른 수집기와 공유한다

BASE = "https://www.kli.re.kr"
LIST_URL = f"{BASE}/menu.es?mid=a10201010000"
VIEW_URL = f"{BASE}/board.es?mid=a10201010100&bid=0002&act=view&list_no={{no}}"
DOWNLOAD_URL = f"{BASE}/boardDownload.es?bid=0002&list_no={{no}}&seq=1"

# 표의 행 이름 → 내부 지표코드. 취업자 '수준'(28,987천명)이 아니라 '증감수'를 쓴다.
LABEL_TO_INDICATOR = {
    "(증감수)": "emp_change",
    "실업률": "unemp_rate",
    "고용률": "emp_rate",
}
# 표는 천명 단위, 아카이브는 만명 단위다
SCALE = {"emp_change": 0.1}
# 이 보고서가 실제로 다루는 지표 — LABEL_TO_INDICATOR 의 값 집합이다. 성장률·
# 물가는 이 보고서가 다루지 않는다(머리말 참고).
INDICATORS = frozenset(LABEL_TO_INDICATOR.values())

_ITEM = re.compile(
    r'href="(?P<href>[^"]*list_no=(?P<no>\d+)[^"]*)"[^>]*>(?P<title>[^<]*전망[^<]*)</a>')
_DATE = re.compile(r"(20\d{2})[.-](\d{2})[.-](\d{2})")
_TABLE_CAPTION = re.compile(r"<표\s*\d+>\s*[^\n]*고용\s*전망")
_TABLE_END = re.compile(r"^\s*(?:주\s*[:：]|자료\s*[:：])")


def forecast_table(page_text: str) -> str:
    """전망표 구간만 잘라낸다.

    표 앞뒤로 서술이 길게 붙어 있어 페이지를 통째로 넘기면 다른 표의 머리글을
    헤더로 잘못 잡는다.
    """
    match = _TABLE_CAPTION.search(page_text)
    if not match:
        raise ValueError("페이지에서 고용 전망 표를 찾지 못했다")
    # 캡션 줄은 뺀다 — "...하반기 및 ... 연간 고용 전망" 의 기간 낱말이 헤더로
    # 딸려 들어가면 열 복원이 어긋난다
    caption_end = page_text.find(chr(10), match.start())
    lines = page_text[caption_end + 1:].split(chr(10))
    out = []
    for line in lines:
        if out and _TABLE_END.match(line):
            break
        out.append(line)
    return "\n".join(out)


def parse(page_text: str, issue: Issue, source_url: str,
          source_page: int) -> list[ForecastRecord]:
    values = pdf.parse_summary_table(forecast_table(page_text), LABEL_TO_INDICATOR)
    scaled = {
        key: round(value * SCALE.get(key[0], 1.0), 2) for key, value in values.items()
    }
    return report.records_from_values(
        scaled, org="KLI", org_name_ko="한국노동연구원", issue=issue,
        source_url=source_url, source_page=source_page,
    )


def parse_list(page_html: str) -> list[Issue]:
    """게시판 목록에서 회차를 최신순으로 준다."""
    issues = []
    for m in _ITEM.finditer(page_html):
        title = html_lib.unescape(m.group("title")).strip()
        if "노동시장" not in title:
            continue
        issues.append(Issue(title=title, published_at=None,
                            url=VIEW_URL.format(no=m.group("no"))))
    return issues


def issue_date(view_html: str) -> date:
    match = _DATE.search(view_html)
    if not match:
        raise ValueError("본문에서 발표일을 찾지 못했다")
    return datetime.strptime("".join(match.groups()), "%Y%m%d").date()


def _list_no(url: str) -> str:
    return re.search(r"list_no=(\d+)", url).group(1)


def list_issues() -> list[Issue]:
    issues = parse_list(http.get(LIST_URL).text)
    if not issues:
        raise ValueError("목록에서 노동시장 전망 회차를 찾지 못했다")
    dated = [
        issue._replace(published_at=issue_date(http.get(issue.url).text))
        for issue in issues
    ]
    return sorted(dated, key=lambda i: i.published_at, reverse=True)


def collect_issue(issue: Issue) -> list[ForecastRecord]:
    url = DOWNLOAD_URL.format(no=_list_no(issue.url))
    pages = pdf.page_texts(http.get(url).content)
    for page_no, text in enumerate(pages, start=1):
        if not _TABLE_CAPTION.search(text):
            continue
        try:
            return parse(text, issue, url, page_no)
        except ValueError:
            # 표 차례에도 같은 캡션이 나온다 — 표가 아닌 쪽은 건너뛴다
            continue
    raise ValueError(f"{issue.title}: 고용 전망 표를 실은 쪽을 찾지 못했다")


def collect_issue_rationales(issue: Issue) -> list["Rationale"]:
    """그 회차의 근거 문장을 준다. 고용 전망 표를 못 찾으면 빈 리스트.

    이 보고서는 표 앞뒤 서술이 표와 같은 쪽에 실린다(실측: 2025년 12월호
    — kli_2026_forecast 픽스처가 그 쪽 원문 그대로다) — KEIS 처럼 앞뒤
    쪽을 따로 읽을 필요가 없다. parse() 는 forecast_table() 로 표 구간만
    잘라 쓰지만, 여기서는 서술까지 담긴 쪽 원문 전체를 report.
    rationales_from_text 에 넘긴다.

    indicators 를 INDICATORS(이 보고서가 실제로 다루는 지표)로 한정한다.
    같은 쪽에는 "이러한 긍정적 전망의 주요 원인으로는 …" 처럼 성장률을
    말하는 서술도 있지만(실측), 이 기관은 성장률을 전망하지 않으므로
    gdp_growth 근거로 저장하면 안 된다.
    """
    url = DOWNLOAD_URL.format(no=_list_no(issue.url))
    pages = pdf.page_texts(http.get(url).content)
    for page_no, text in enumerate(pages, start=1):
        if not _TABLE_CAPTION.search(text):
            continue
        try:
            parse(text, issue, url, page_no)
        except ValueError:
            # 표 차례에도 같은 캡션이 나온다 — 표가 아닌 쪽은 건너뛴다
            continue
        return report.rationales_from_text(
            text, org="KLI", issue=issue,
            indicators=sorted(INDICATORS), source_url=url, source_page=page_no)
    return []


def collect(today: date) -> list[ForecastRecord]:
    return collect_issue(list_issues()[0])
