"""담을 게시판은 코드가 아니라 boards.json 에 있다.

사이트는 "이건 보고서 게시판"이라고 알려주지 않는다. 사람이 고른 목록을 여기서
읽고, 목록에 없는 게시판이 사이트에 나타나면 경고만 낸다 — 자동으로 담지 않는다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal, Optional
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
    # 항목이 앵커가 아니라 버튼인 게시판(KDI 경제동향)의 목록 모양.
    list_style: str = 'list'
    enabled: bool = True
    collapse: bool = False
    category_keep: Optional[str] = None
    # KEIS 는 목록 항목이 초록·PDF 를 다 들고 있고 상세 페이지가 따로 없다.
    # 켜져 있으면 수집기가 상세를 다시 요청하지 않는다.
    detail_in_list: bool = False
    # 한국은행은 게시판을 menuNo 로 구분한다. 목록 주소가 전 게시판 공통이라
    # list_url 만으로는 어느 게시판인지 알 수 없다.
    menu_no: Optional[str] = None
    # 상세 본문 블록(div.dbdata)이 게시판마다 다른 것을 담는다 — 초록이기도,
    # 목차이기도, "첨부파일 참조" 안내문이기도 하다. 실측표는 스펙 §3-3.
    # 이 값을 바꾸면 그 게시판만 재수집해야 한다(분류가 수집 시점에 일어난다).
    body: Literal['abstract', 'toc', 'none'] = 'abstract'
    # 같은 연구를 두 지역본부가 각각 올리는 게시판이 있다(BOK 조사연구자료에서 7쌍).
    # 글 번호가 달라 id 로는 안 잡힌다. 반대로 연속간행물에는 고정 제목 칼럼이 흔해서
    # (KIET 월간 산업경제의 '실물경제 주요 지표', 이슈페이퍼의 '새해 한국 경제에 바란다')
    # 전 게시판에 걸면 멀쩡한 회차가 사라진다. 그래서 게시판이 지정한 경우에만 없앤다.
    dedupe_titles: bool = False


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
