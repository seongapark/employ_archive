"""KDI 경제전망 수집기.

/research/economy 는 최신 회차 본문이면서 지난 회차로 가는 드롭다운
(yearSelectUpDown)도 같이 싣는다. 드롭다운은 pub_no 와 표시 라벨만 줄 뿐
정식 제목·발표일이 없어, 회차마다 본문을 열어 parse_issue 로 실제 값을
읽는다. 본문에서 회차 제목·발표일과 장별 PDF 링크를 얻어 요약 장을 읽는다.
KDI PDF 표지에는 발표일이 없으므로 날짜는 반드시 본문 페이지에서 가져온다.
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
ISSUE_URL = f"{BASE}/research/economy?pub_no={{no}}"

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
# 드롭다운 select 본문만 잘라 그 안의 option 만 줍는다 — 페이지 다른 곳의
# option 태그(있다면)를 회차로 잘못 세는 사고를 막는다
_ISSUE_SELECT = re.compile(
    r'<select id="yearSelectUpDown"[^>]*>(?P<body>.*?)</select>', re.S,
)
_ISSUE_OPTION = re.compile(r'<option value="(\d+)"')


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


def parse_issue_list(page_html: str) -> list[str]:
    """회차 선택 드롭다운에서 pub_no 를 문서 순서(최신 먼저)대로 돌려준다.

    select 가 없으면 빈 리스트를 조용히 돌려주는 대신 예외를 던진다 —
    그러면 뒤에서 회차가 하나도 없는 것과 구별이 안 돼 백필이 조용히
    아무 일도 안 하고 끝나 버린다.
    """
    match = _ISSUE_SELECT.search(page_html)
    if not match:
        raise ValueError("페이지에서 회차 선택 목록을 찾지 못했다")
    return _ISSUE_OPTION.findall(match.group("body"))


def parse(text: str, issue: Issue, source_url: str, source_page: int) -> list[ForecastRecord]:
    return report.records_from_table(
        text, LABEL_TO_INDICATOR,
        org="KDI", org_name_ko="KDI",
        issue=issue, source_url=source_url, source_page=source_page,
    )


def list_issues() -> list[Issue]:
    """드롭다운에 남은 회차를 최신순으로 준다.

    드롭다운은 pub_no 와 표시 라벨(예: "2025 상반기")만 줄 뿐 정식 제목과
    발표일이 없다. 회차마다 본문을 열어 parse_issue 로 실제 값을 읽는다.
    """
    pub_nos = parse_issue_list(http.get(LIST_URL).text)
    if not pub_nos:
        raise ValueError("드롭다운에서 회차를 찾지 못했다")
    issues = []
    for no in pub_nos:
        url = ISSUE_URL.format(no=no)
        issues.append(parse_issue(http.get(url).text, url))
    return issues


def collect_issue(issue: Issue) -> list[ForecastRecord]:
    page_html = http.get(issue.url).text
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


def collect(today: date) -> list[ForecastRecord]:
    return collect_issue(list_issues()[0])
