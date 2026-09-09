"""담을 게시판은 코드가 아니라 boards.json 에 있다.

사이트는 "이건 보고서 게시판"이라고 알려주지 않는다. 사람이 고른 목록을 여기서
읽고, 목록에 없는 게시판이 사이트에 나타나면 경고만 낸다 — 자동으로 담지 않는다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from pydantic import BaseModel

BOARDS_PATH = Path(__file__).resolve().parent.parent / 'data' / 'boards.json'

# 메뉴에서 "목록 게시판"으로 볼 주소. 상세·다운로드·정적 페이지는 제외한다.
_LIST_HREF = re.compile(r'(List\b|list\.do|menu\.es\?mid=)')


class Board(BaseModel):
    id: str
    org: str
    name: str
    series: str
    list_url: str
    item_re: str
    # 게시판마다 페이저 주소가 다르다(KLI 만 해도 rschRptpList / prdclList /
    # issuePaperList 셋). 목록 주소로 페이지를 만들어 낼 수 없으므로 실측한
    # 템플릿을 그대로 둔다. {page} 자리에 페이지 번호가 들어간다.
    page_url: Optional[str] = None
    # {page} 에 번호 대신 이 값들이 차례로 들어간다. KDI 경제동향은 페이지가
    # 아니라 연도로 넘긴다(monTrends?year=2025).
    page_values: Optional[list[str]] = None
    single_page: bool = False
    # 게시판마다 번호 공간이 다르다(report_no / art_no / paper_no). 접두어가
    # 없으면 다른 게시판의 다른 보고서가 같은 id 를 갖는다.
    id_prefix: str = ''
    filter: bool = False
    enabled: bool = True
    collapse: bool = False
    category_keep: Optional[str] = None
    # KEIS 는 목록 항목이 초록·PDF 를 다 들고 있고 상세 페이지가 따로 없다.
    # 켜져 있으면 수집기가 상세를 다시 요청하지 않는다.
    detail_in_list: bool = False


def load_boards(path: Path | str | None = None) -> list[Board]:
    p = Path(path or BOARDS_PATH)
    rows = json.loads(p.read_text(encoding='utf-8'))
    return [Board.model_validate(r) for r in rows]


def _key(url: str) -> str:
    """호스트를 뺀 경로+질의. 상대·절대 주소를 같은 자로 잰다."""
    parts = urlsplit(url)
    return parts.path + (('?' + parts.query) if parts.query else '')


def unregistered(menu_html: str, org: str, boards: list[Board]) -> list[str]:
    known = {_key(b.list_url) for b in boards if b.org == org}
    found: list[str] = []
    for href in re.findall(r'href="([^"]+)"', menu_html):
        if not _LIST_HREF.search(href):
            continue
        if _key(href) in known or href in found:
            continue
        found.append(href)
    return found
