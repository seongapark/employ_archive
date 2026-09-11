"""한국은행(BOK) 목록·상세 파서.

목록 페이지(list.do)는 자바스크립트가 그린다. 그리는 주체인 AJAX 원본
listCont.do 가 완성된 HTML 을 그대로 주므로 그쪽을 읽는다 — 쪽당 100건에
pageIndex 페이징이라 2021년까지 백필된다.

(고용전망 도메인의 BOK 수집기는 RSS 를 쓴다. 그건 최신 회차만 필요해서다.
여기는 백필이 필요해 경로가 다르다 — 코드를 공유하지 않는다.)

게시판 여덟이 전부 이 파서 하나로 처리된다. 목록 엔드포인트가 하나고,
상세는 전부 /portal/bbs/<bbsId>/view.do?nttId= 이며 bbsId 는 목록 앵커에
박혀 있어 boards.json 에 적을 필요가 없다. 구분자는 menuNo 뿐이다.
"""
from __future__ import annotations

import re
from urllib.parse import urlencode

from ..boards import Board
from ..models import RawReport, normalize_published, report_id
from . import common

BASE = 'https://www.bok.or.kr'
LIST_ENDPOINT = f'{BASE}/portal/singl/newsData/listCont.do'
PAGE_UNIT = 100

_ROW = re.compile(r'<li class="bbsRowCls">(.*?)</li>', re.S)
_DATE = re.compile(r'class="date"><span class="sr-only">[^<]*</span>\s*([\d.]+)')
_DEPT = re.compile(r'class="depart"><span class="sr-only">[^<]*</span>\s*([^<]*)')
_LINK = re.compile(
    r'<a href="(/portal/bbs/[A-Z]\d+/view\.do\?nttId=(\d+)[^"]*)"[^>]*class="title">(.*?)</a>',
    re.S)


def list_url(board: Board, page: int) -> str:
    query = {
        'pageIndex': str(page), 'targetDepth': '3', 'menuNo': board.menu_no or '',
        'syncMenuChekKey': '1', 'searchCnd': '1', 'searchKwd': '',
        'depth2': '201157', 'depth3': board.menu_no or '',
        'date': '', 'sdate': '', 'edate': '', 'sort': '1',
        'pageUnit': str(PAGE_UNIT),
    }
    return f'{LIST_ENDPOINT}?{urlencode(query)}'


def parse_list(html: str, board: Board) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for block in _ROW.findall(html or ''):
        link = _LINK.search(block)
        date = _DATE.search(block)
        if not (link and date):
            continue
        native_id = link.group(2)
        if native_id in seen:
            continue
        title = common.text(link.group(3))
        if not title:
            continue
        dept = _DEPT.search(block)
        seen.add(native_id)
        items.append({
            'native_id': native_id,
            'detail_url': common.absolute(BASE, link.group(1).replace('&amp;', '&')),
            'published_raw': date.group(1),
            'title': title,
            'dept': common.text(dept.group(1)) if dept else '',
        })
    return items
