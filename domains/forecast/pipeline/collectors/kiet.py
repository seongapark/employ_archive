"""산업연구원 「경제·산업 전망」 수집기.

연 2회(연간 전망·하반기 전망) 나온다. 목록에서 회차를 찾아 상세 페이지의
JSON-LD 에서 발표일을, 첨부 PDF 에서 <표> 국내 주요 거시경제지표 전망을 읽는다.

이 표에는 성장률만 우리 지표와 겹친다. 취업자·실업률은 보고서 본문에 서술과
실적으로만 나오고 전망표가 없다. 물가도 이 표에 없다.
"""
from __future__ import annotations

import html as html_lib
import re
from datetime import date, datetime

from .. import http, pdf, report
from ..models import ForecastRecord
from ..report import Issue

BASE = "https://www.kiet.re.kr"
LIST_URL = f"{BASE}/trends/ecolookList"
VIEW_URL = f"{BASE}/trends/ecolookView?ecolook_no={{no}}"

LABEL_TO_INDICATOR = {"실질GDP": "gdp_growth"}

# 13대 주력산업편은 같은 회차의 산업 부록이라 거시 전망표가 없다
# 제목은 <a> 안의 <strong> 에 들어 있다
_ITEM = re.compile(
    r'href="\.?/?(?:trends/)?ecolookView\?ecolook_no=(?P<no>\d+)[^"]*"[^>]*>'
    r'\s*<strong>(?P<title>[^<]*경제[·ㆍ]\s*산업\s*전망[^<]*)</strong>',
    re.S,
)
_INDUSTRY_SUPPLEMENT = re.compile(r"주력산업편")
_PUBLISHED = re.compile(r'"datePublished"\s*:\s*"(20\d{2})\.(\d{2})\.(\d{2})"')
_TABLE_CAPTION = re.compile(r"<표\s*[\d-]+>\s*[^\n]*거시경제지표\s*전망")
_TABLE_END = re.compile(r"^\s*(?:주\s*[:：]|자료\s*[:：])")
_DOWNLOAD = re.compile(r'href="(/common/file/userDownload\?atch_no=[^"]+)"')


def macro_table(page_text: str) -> str:
    """거시경제지표 전망표 구간만 잘라낸다(캡션 줄 제외)."""
    match = _TABLE_CAPTION.search(page_text)
    if not match:
        raise ValueError("페이지에서 거시경제지표 전망 표를 찾지 못했다")
    caption_end = page_text.find("\n", match.start())
    out = []
    for line in page_text[caption_end + 1:].split("\n"):
        if out and _TABLE_END.match(line):
            break
        out.append(line)
    return "\n".join(out)


def parse(page_text: str, issue: Issue, source_url: str,
          source_page: int) -> list[ForecastRecord]:
    values = pdf.parse_summary_table(macro_table(page_text), LABEL_TO_INDICATOR)
    return report.records_from_values(
        values, org="KIET", org_name_ko="산업연구원", issue=issue,
        source_url=source_url, source_page=source_page,
    )


def parse_list(page_html: str) -> list[Issue]:
    issues, seen = [], set()
    for m in _ITEM.finditer(page_html):
        title = html_lib.unescape(m.group("title")).strip()
        if _INDUSTRY_SUPPLEMENT.search(title) or m.group("no") in seen:
            continue
        seen.add(m.group("no"))
        issues.append(Issue(title=title, published_at=None,
                            url=VIEW_URL.format(no=m.group("no"))))
    return issues


def issue_date(view_html: str) -> date:
    match = _PUBLISHED.search(view_html)
    if not match:
        raise ValueError("상세 페이지에서 발표일(datePublished)을 찾지 못했다")
    return datetime.strptime("".join(match.groups()), "%Y%m%d").date()


def parse_pdf_link(view_html: str) -> str:
    match = _DOWNLOAD.search(view_html)
    if not match:
        raise ValueError("상세 페이지에서 첨부를 찾지 못했다")
    return BASE + html_lib.unescape(match.group(1))


def list_issues() -> list[Issue]:
    issues = parse_list(http.get(LIST_URL).text)
    if not issues:
        raise ValueError("목록에서 경제·산업 전망 회차를 찾지 못했다")
    dated = [i._replace(published_at=issue_date(http.get(i.url).text)) for i in issues]
    return sorted(dated, key=lambda i: i.published_at, reverse=True)


def collect_issue(issue: Issue) -> list[ForecastRecord]:
    url = parse_pdf_link(http.get(issue.url).text)
    pages = pdf.page_texts(http.get(url).content)
    for page_no, text in enumerate(pages, start=1):
        if not _TABLE_CAPTION.search(text):
            continue
        try:
            return parse(text, issue, url, page_no)
        except ValueError:
            # 표 차례에도 같은 캡션이 나온다 — 표가 아닌 쪽은 건너뛴다
            continue
    raise ValueError(f"{issue.title}: 거시경제지표 전망 표를 실은 쪽을 찾지 못했다")


def collect(today: date) -> list[ForecastRecord]:
    return collect_issue(list_issues()[0])
