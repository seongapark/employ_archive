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

from .. import http
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
    """
    listed = []
    for row in _ROW.findall(page_html):
        subject = _SUBJECT.search(row)
        published = _DATE.search(row)
        pdf = _PDF.search(row)
        if not (subject and published and pdf):
            continue
        listed.append(ListedIssue(
            issue=Issue(
                title=html_lib.unescape(subject.group("title")).strip(),
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
