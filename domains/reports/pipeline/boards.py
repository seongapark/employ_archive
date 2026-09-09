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
    page_param: Optional[str] = None
    page_size_param: Optional[str] = None
    page_size: Optional[int] = None
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
