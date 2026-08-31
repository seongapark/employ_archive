"""한국고용정보원 「고용동향브리프」 수집기.

원칙은 연 1회다 — 연말호가 이듬해 연간 전망을 싣는다. 다만 2026년은 하반기
전망호(제5호)가 따로 나왔다. 회차 번호로 전망호를 특정할 수 없다는 뜻이라,
새 호가 올라오면 열어 보고 전망표가 있는지 확인한다.

이 브리프의 PDF 에는 텍스트 레이어가 없다(ocr.py 머리말 참고). 쪽을
렌더링해 읽으므로 다른 수집기보다 느리고, 그래서 두 단계로 나눈다 —
낮은 해상도로 후보 쪽을 좁힌 뒤 그 쪽만 정밀하게 읽는다.
"""
from __future__ import annotations

import html as html_lib
import re
from datetime import date, datetime
from typing import NamedTuple

from .. import http, report
from ..models import ForecastRecord
from ..report import Issue

BASE = "https://www.keis.or.kr"
LIST_URL = f"{BASE}/keis/ko/proj/118/pblc/list.do"
DETAIL_URL = f"{BASE}/keis/ko/proj/118/pblc/detail.do?categoryIdx={{category}}&pubIdx={{pub}}"

_ROW = re.compile(r"<tr[\s>].*?</tr>", re.S)
_SUBJECT = re.compile(
    r"goDetail\('categoryIdx=(?P<category>\d+)&(?:amp;)?pubIdx=(?P<pub>\d+)'\)[^>]*>"
    r"(?P<title>.*?)</a>", re.S)
_DATE = re.compile(r'class="cell-date".*?<span>(\d{4})\.(\d{2})\.(\d{2})</span>', re.S)
_PDF = re.compile(r'href="(/keis/ko/cmmn/download\.do\?[^"]+)"')


class ListedIssue(NamedTuple):
    issue: Issue
    pdf_url: str


def parse_list(page_html: str) -> list[ListedIssue]:
    """목록 페이지의 <tr> 을 회차로 옮긴다.

    목록 맨 위 대표 게시물 블록은 1번 행과 같은 회차를 한 번 더 싣는다.
    <tr> 만 읽어 중복을 피한다.

    subject 앵커(goDetail(...))가 없는 행은 헤더·레이아웃용 행이라 조용히
    건너뛴다. 하지만 subject 앵커가 있는데 게시일이나 PDF 링크가 없다면
    그 행은 분명 게시물인데 못 읽은 것이다 — 서식이 바뀐 신호이므로
    조용히 넘기지 않고 실패시킨다. 그래야 매일 도는 수집기가 1번 행을
    건너뛰고 이미 있는 회차를 다시 모아 added: 0 으로 조용히 끝나는
    사고를 막는다.
    """
    listed = []
    for row in _ROW.findall(page_html):
        subject = _SUBJECT.search(row)
        if not subject:
            continue
        title = html_lib.unescape(subject.group("title")).strip()
        published = _DATE.search(row)
        pdf = _PDF.search(row)
        if not published:
            raise ValueError(f"{title}: 게시일을 찾지 못했다 — 서식이 바뀌었다")
        if not pdf:
            raise ValueError(f"{title}: PDF 다운로드 링크를 찾지 못했다 — 서식이 바뀌었다")
        listed.append(ListedIssue(
            issue=Issue(
                title=title,
                published_at=datetime.strptime(
                    "".join(published.groups()), "%Y%m%d").date(),
                url=DETAIL_URL.format(category=subject.group("category"),
                                      pub=subject.group("pub")),
            ),
            pdf_url=BASE + html_lib.unescape(pdf.group(1)),
        ))
    return listed


def list_issues() -> list[ListedIssue]:
    listed = parse_list(http.get(LIST_URL).text)
    if not listed:
        raise ValueError("목록에서 고용동향브리프 회차를 찾지 못했다")
    return listed


# 연도 칸은 '2026년', 잠정치는 '2026년p'. OCR 이 그 p 를 6·0 으로도 읽는다.
_YEAR_CELL = re.compile(r"(20\d{2})년[a-zA-Z0-9]?")
_HALF_WORDS = {"상반기": "h1", "하반기": "h2"}
# 헤더 줄로 인정할 최소 연도 개수. 본문 문장에도 연도가 한둘 나온다.
_MIN_YEARS = 3


def header_columns(lines: list[str]) -> list[tuple[int, str]]:
    """헤더에서 열 순서대로 (연도, 기간) 을 만든다.

    이 표에는 '연간' 토큰이 없다 — 연도 칸 자체가 연간이고, 반기가 있을 때만
    마지막 연도의 하위 열로 오른쪽에 붙는다. 기존 pdf._columns 가 기간 토큰을
    연도 블록으로 묶는 것과 구조가 달라 여기서 따로 만든다.
    """
    for index, line in enumerate(lines):
        years = [int(y) for y in _YEAR_CELL.findall(line)]
        if len(years) < _MIN_YEARS:
            continue
        columns = [(year, "annual") for year in years]
        following = lines[index + 1] if index + 1 < len(lines) else ""
        halves = [_HALF_WORDS[word] for word in ("상반기", "하반기")
                  if word in following]
        return columns + [(years[-1], half) for half in halves]
    raise ValueError("표에서 연도 줄을 찾지 못했다")


# 표의 대분류. '(증감)' 이 여러 번 나오므로 직전 대분류를 기억해야 한다.
_SECTIONS = ("생산가능인구", "경제활동인구", "취업자", "비경제활동인구")
# (대분류, 행 이름) -> 지표코드. 대분류가 필요 없는 행은 왼쪽을 None 으로 둔다.
LABEL_TO_INDICATOR = {
    ("취업자", "(증감)"): "emp_change",
    (None, "실업률"): "unemp_rate",
    (None, "고용률"): "emp_rate",
}
# 표는 천명 단위, 아카이브는 만명 단위다
SCALE = {"emp_change": 0.1}
REQUIRED_INDICATORS = frozenset({"emp_change", "emp_rate", "unemp_rate"})

_NUMBER = re.compile(r"^[(\[]?[-−]?[\d,]+(?:\.\d+)?[)\]]?$")
_WRAPPING_PAREN = re.compile(r"^[(\[]|[)\]]$")


def _number(token: str) -> float | None:
    """'(146)' · '-0.8' · '29,203' 을 숫자로. 아니면 None.

    이 표는 증감·증가율을 괄호로 감싸므로 기존 pdf._NUMBER 로는 못 읽는다.
    """
    if not _NUMBER.match(token):
        return None
    cleaned = _WRAPPING_PAREN.sub("", token)
    return float(cleaned.replace(",", "").replace("−", "-"))


def _split_row(line: str) -> tuple[str, list[float]]:
    """줄을 (행 이름, 숫자들) 로 가른다. 첫 숫자 앞까지가 이름이다."""
    words, numbers = [], []
    for token in line.split():
        value = _number(token)
        if value is None and not numbers:
            words.append(token)
        elif value is not None:
            numbers.append(value)
    return "".join(words), numbers


def parse_table(text: str) -> dict[tuple[str, int, str], float]:
    """전망표 원문에서 {(지표, 연도, 기간): 값} 을 뽑는다."""
    lines = [line for line in text.split("\n") if line.strip()]
    columns = header_columns(lines)

    values: dict[tuple[str, int, str], float] = {}
    section = None
    for line in lines:
        label, numbers = _split_row(line)
        if label in _SECTIONS:
            section = label
        if len(numbers) != len(columns):
            continue
        indicator = (LABEL_TO_INDICATOR.get((section, label))
                     or LABEL_TO_INDICATOR.get((None, label)))
        if indicator is None:
            continue
        scale = SCALE.get(indicator, 1.0)
        for (year, period), value in zip(columns, numbers):
            values[(indicator, year, period)] = round(value * scale, 2)

    found = {indicator for indicator, _, _ in values}
    missing = REQUIRED_INDICATORS - found
    if missing:
        raise ValueError(f"전망표에서 지표를 찾지 못했다: {sorted(missing)}")
    return values


def parse(text: str, issue: Issue, source_url: str,
          source_page: int) -> list[ForecastRecord]:
    return report.records_from_values(
        parse_table(text), org="KEIS", org_name_ko="한국고용정보원", issue=issue,
        source_url=source_url, source_page=source_page,
    )
