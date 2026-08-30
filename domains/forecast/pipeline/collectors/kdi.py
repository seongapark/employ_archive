"""KDI 경제전망 수집기.

/research/economy 가 곧 최신 회차 본문이라 목록을 따로 긁을 필요가 없다.
본문에서 회차 제목·발표일과 장별 PDF 링크를 얻어 요약 장을 읽는다.
KDI PDF 표지에는 발표일이 없으므로 날짜는 반드시 이 페이지에서 가져온다.
"""
from __future__ import annotations

import html as html_lib
import re
from datetime import date, datetime

from .. import http, pdf, report
from ..models import ForecastRecord
from ..report import Issue  # 두 수집기가 같은 회차 표현을 쓴다

BASE = "https://www.kdi.re.kr"
LIST_URL = f"{BASE}/research/economy"

# 요약표 행 이름(공백·단위·각주 제거) → 내부 지표코드. KDI 표에는 고용률이 없다.
LABEL_TO_INDICATOR = {
    "국내총생산": "gdp_growth",
    "소비자물가": "cpi",
    "취업자수(증감)": "emp_change",
    "실업률": "unemp_rate",
}

# 요약표로 인정하는 최소 지표. 동향 장에 실린 다른 표들을 거른다
REQUIRED_INDICATORS = {"gdp_growth", "cpi", "emp_change", "unemp_rate"}

# 회차 제목 앞에 네비게이션용 <h2>가 여럿 있으므로 h2 경계를 넘지 않도록 막는다
_TITLE_BLOCK = re.compile(
    r"<h2>(?P<title>(?:(?!</?h2).)*?)"
    r"<p>(?P<date>20\d{2}\.\d{2}\.\d{2})</p>\s*</h2>",
    re.S,
)
_CHAPTER = re.compile(
    r'<li class="down"><p>(?P<label>.*?)</p>'
    r"<button[^>]*location\.href='(?P<href>/file/download\?atch_no=[^']+)'",
    re.S,
)


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def parse_issue(page_html: str, url: str) -> Issue:
    match = _TITLE_BLOCK.search(page_html)
    if not match:
        raise ValueError("본문에서 회차 제목·발표일을 찾지 못했다")
    return Issue(
        title=re.sub(r"\s+,", ",", _text(match.group("title"))),
        published_at=datetime.strptime(match.group("date"), "%Y.%m.%d").date(),
        url=url,
    )


def parse_chapters(page_html: str) -> list[tuple[str, str]]:
    """(장 이름, 내려받기 URL) 을 본문에 실린 순서대로 돌려준다."""
    return [
        (_text(m.group("label")), BASE + html_lib.unescape(m.group("href")))
        for m in _CHAPTER.finditer(page_html)
    ]


def parse(text: str, issue: Issue, source_url: str, source_page: int) -> list[ForecastRecord]:
    return report.records_from_table(
        text, LABEL_TO_INDICATOR,
        org="KDI", org_name_ko="KDI",
        issue=issue, source_url=source_url, source_page=source_page,
    )


def collect(today: date) -> list[ForecastRecord]:
    page_html = http.get(LIST_URL).text
    issue = parse_issue(page_html, LIST_URL)
    for _, url in parse_chapters(page_html):
        # 장은 본문 순서대로 나오지만 표가 어디 실릴지는 회차마다 다르다. 앞 장이
        # 502거나 표 없는 첨부여도 뒷 장을 마저 봐야 하므로 장 단위로 실패를 가둔다.
        try:
            found = pdf.find_summary_table(
                pdf.page_texts(http.get(url).content), LABEL_TO_INDICATOR, REQUIRED_INDICATORS
            )
        except Exception:
            continue
        if found is None:
            continue
        page_no, text = found
        return parse(text, issue, url, page_no)
    raise ValueError(f"{issue.title}: 요약표를 실은 장을 찾지 못했다")
