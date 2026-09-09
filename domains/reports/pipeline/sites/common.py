"""네 파서가 함께 쓰는 조각들. 기관을 모른다."""
from __future__ import annotations

import html as html_mod
import re
from urllib.parse import quote, urljoin

from ..boards import Board

_TAG = re.compile(r'<[^>]+>')
_WS = re.compile(r'[ \t\r\f\v ]+')
_DATE = re.compile(r'(20\d{2})[-.\s]{1,3}(\d{1,2})(?:[-.\s]{1,3}(\d{1,2}))?')


def page_url(board: Board, page: int) -> str:
    """게시판의 n번째 페이지 주소.

    게시판마다 페이저 주소가 달라 boards.json 의 템플릿을 그대로 쓴다.
    KDI 경제동향처럼 페이지가 아니라 연도로 넘기는 게시판은 page_values 를 쓴다.
    """
    tmpl = board.page_url or board.list_url
    if board.page_values:
        if page > len(board.page_values):
            return ''            # 더 볼 페이지가 없다
        value = board.page_values[page - 1]
    else:
        value = str(page)
    url = tmpl.replace('{page}', value)
    # 질의에 한글이 들어가는 게시판이 있다(KLI 의 sch_prdcl=노동리뷰).
    return quote(url, safe=":/?&=%#+,")


def text(fragment: str) -> str:
    """태그를 걷어내고 엔티티를 푼 뒤 공백을 다듬는다."""
    s = _TAG.sub(' ', fragment or '')
    s = html_mod.unescape(s)
    s = _WS.sub(' ', s)
    return s.strip()


def lines(fragment: str) -> list[str]:
    """<br> 로 끊긴 덩어리를 줄 목록으로. 목차에 쓴다."""
    s = re.sub(r'<br\s*/?>', '\n', fragment or '', flags=re.I)
    out = [text(line) for line in s.split('\n')]
    return [line for line in out if line]


def find_date(fragment: str) -> str | None:
    m = _DATE.search(fragment or '')
    if not m:
        return None
    y, mo, d = m.group(1), m.group(2), m.group(3)
    return f'{y}.{mo}.{d}' if d else f'{y}.{mo}'


def absolute(base: str, href: str) -> str:
    return urljoin(base, html_mod.unescape(href or '').strip())


def rows(html: str, tag: str = 'tr') -> list[str]:
    """여는 태그를 기준으로 항목 블록을 자른다."""
    parts = re.split(rf'(?=<{tag}[\s>])', html or '')
    return parts[1:] if len(parts) > 1 else []
