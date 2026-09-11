"""한국노동연구원 「노동시장 평가와 전망」 수집기.

연 2회(상반기 평가·연간 전망) 나온다. **「KLI 고용·노동브리프」 게시판**에서
회차를 찾아 첨부 PDF 의 <표 N> 고용 전망 표를 읽는다.

## 왜 노동리뷰 게시판이 아니라 브리프인가 (2026-09-11 에 갈아탔다)

예전에는 `노동시장/노사관계전망` 게시판(`bid=0002`)을 봤다. 같은 보고서가 두 곳에
실리는데 그 게시판이 **늦고 날짜도 부정확했다**:

  - **늦는다.** 2026년 하반기 전망이 브리프에 2026-08-06 로 올라온 뒤에도 그
    게시판에는 한 달 넘게 안 올라왔다. 노동리뷰 8월호 특집으로 먼저 나온다.
  - **날짜가 등록일이다.** 옛 회차 넷이 **전부 2023-05-19** 로 몰려 있었다
    (하루에 몰아 올린 등록일). id 가 `kli-<연-월>-...` 이라 넷이 겹쳐 하나만
    저장됐다. 브리프의 출판일은 2021-12-15 · 2022-08-16 · 2022-12-20 로 갈린다.
    2024년 하반기도 브리프 2024-08-30 발간인데 그 게시판은 2024-10-04 였다(35일 차이).

브리프 목록은 제목·출판일·PDF 링크를 **한 표에 다 갖고 있어** 회차마다 상세
페이지를 여는 왕복도 사라진다(상세 페이지는 PDF 를 다시 확인할 때만 연다).

이 보고서는 노동시장만 다뤄 성장률·물가가 없다. 대신 취업자 증감·실업률·고용률을
반기까지 실어, 고용전망 아카이브에는 기관 중 가장 잘 맞는 자료다.
"""
from __future__ import annotations

import html as html_lib
import re
from datetime import date

from .. import http, pdf, report
from ..models import ForecastRecord
from ..report import Issue  # 회차 표현은 다른 수집기와 공유한다

BASE = "https://www.kli.re.kr"
# sch_prdcl 로 간행물을 고른다 — 이슈페이퍼 게시판에는 다른 간행물도 섞여 있다.
LIST_URL = (f"{BASE}/kli/issuePaperList.es?mid=a10104010000"
            "&sch_prdcl=KLI%EA%B3%A0%EC%9A%A9%EB%85%B8%EB%8F%99%EB%B8%8C%EB%A6%AC%ED%94%84")
VIEW_URL = f"{BASE}/kli/issuePaperView.es?pblct_sn={{sn}}&mid=a10104010000"

# 표의 행 이름 → 내부 지표코드. 취업자 '수준'(28,987천명)이 아니라 '증감수'를 쓴다.
LABEL_TO_INDICATOR = {
    "(증감수)": "emp_change",
    "실업률": "unemp_rate",
    "고용률": "emp_rate",
}
# 표는 천명 단위, 아카이브는 만명 단위다
SCALE = {"emp_change": 0.1}
# 이 보고서가 실제로 다루는 지표 — LABEL_TO_INDICATOR 의 값 집합이다. 성장률·
# 물가는 이 보고서가 다루지 않는다(머리말 참고). documents.py 가 근거 문서
# 조회에 쓴다.
INDICATORS = frozenset(LABEL_TO_INDICATOR.values())

# 목록 표의 한 줄에서 상세주소·제목·출판일·PDF 주소를 한꺼번에 읽는다.
_ROW = re.compile(
    r'aria-label="제목"><a href="[^"]*pblct_sn=(?P<sn>\d+)[^"]*"[^>]*>\s*'
    r'(?P<title>[^<]+?)\s*</a></td>.*?'
    r'aria-label="출판일">\s*(?P<y>20\d{2})\.(?P<m>\d{2})\.(?P<d>\d{2})\s*</td>.*?'
    r'href="(?P<pdf>/kliFileDownload\?[^"]+)"',
    re.S,
)
_PDF_LINK = re.compile(r'href="(/kliFileDownload\?[^"]+)"')
# 캡션이 회차마다 흔들린다 — `고용 전망` 도 있고 `고용 수정 전망` 도 있다
# (제115호는 `<표 3> 2026년 고용 수정 전망`). 사이에 낱말이 끼는 것을 허용한다.
_TABLE_CAPTION = re.compile(r"<표\s*\d+>\s*[^\n]*고용[^\n]{0,8}전망")
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
        scaled, org="KLI", org_name_ko="KLI", issue=issue,
        source_url=source_url, source_page=source_page,
    )


def parse_list(page_html: str) -> list[Issue]:
    """목록에서 **전망 회차만** 최신순으로 준다.

    이 게시판에는 브리프의 다른 주제 호도 섞여 있다. 제목에 '노동시장' 과
    '전망' 이 함께 있는 것만 고른다 — 이 시리즈의 제목은 늘
    "… 노동시장 평가와 … 노동시장 전망" 꼴이다.
    """
    issues = []
    for m in _ROW.finditer(page_html):
        title = html_lib.unescape(m.group("title")).strip()
        if "노동시장" not in title or "전망" not in title:
            continue
        issues.append(Issue(
            title=title,
            published_at=date(int(m.group("y")), int(m.group("m")), int(m.group("d"))),
            url=VIEW_URL.format(sn=m.group("sn")),
        ))
    return issues


def pdf_url(view_html: str) -> str:
    """상세 페이지에서 첨부 PDF 주소를 읽는다."""
    match = _PDF_LINK.search(view_html)
    if not match:
        raise ValueError("상세 페이지에서 첨부 PDF 를 찾지 못했다")
    return BASE + html_lib.unescape(match.group(1))


def list_issues() -> list[Issue]:
    issues = parse_list(http.get(LIST_URL).text)
    if not issues:
        raise ValueError("목록에서 노동시장 전망 회차를 찾지 못했다")
    # 발표일이 목록에 이미 있다 — 회차마다 상세 페이지를 여는 왕복이 없다.
    return sorted(issues, key=lambda i: i.published_at, reverse=True)


def collect_issue(issue: Issue) -> list[ForecastRecord]:
    url = pdf_url(http.get(issue.url).text)
    pages = pdf.page_texts(http.get(url).content)
    for page_no, text in enumerate(pages, start=1):
        if not _TABLE_CAPTION.search(text):
            continue
        try:
            records = parse(text, issue, url, page_no)
        except ValueError:
            # 표 차례에도 같은 캡션이 나온다 — 표가 아닌 쪽은 건너뛴다
            continue
        # 표는 읽혔는데 남은 레코드가 없으면 열이 밀렸거나 그 표가 실적뿐이다
        # (records_from_values 가 발표연도 이전 해를 버린다). 빈 손을 성공으로
        # 돌려주면 그 회차가 조용히 사라진다 — moef 와 같은 규칙이다.
        if records:
            return records
    raise ValueError(f"{issue.title}: 고용 전망 표를 실은 쪽을 찾지 못했다")


def collect(today: date) -> list[ForecastRecord]:
    return collect_issue(list_issues()[0])
