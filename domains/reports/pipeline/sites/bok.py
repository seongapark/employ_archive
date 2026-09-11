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


# 상세 본문 블록. class="dbdata" 뒤에 공백이 하나 붙는 게시판도 있어 \s* 로
# 흡수한다. 안쪽에 <div> 가 없어(전부 <p>) 첫 </div> 가 곧 블록의 끝이다.
_BODY = re.compile(r'<div class="dbdata\s*"[^>]*>(.*?)</div>\s*(?:<div|</div>)', re.S)
_FILE = re.compile(r'<a href="(/fileSrc/[^"]+)"')
# 이슈노트·심층연구는 초록 앞에 "본 내용은 ... 확인 가능합니다" 출처 안내문이
# 붙는 회차가 있다. 없는 회차도 있어 없으면 그냥 통과시킨다.
_SOURCE_NOTE = re.compile(
    r'^\s*\*?\s*본 내용은.*?확인 가능합니다\s*\.?', re.S)
_ATTACH_ONLY = re.compile(r'첨부파일')


def _strip_source_note(text: str) -> str:
    return _SOURCE_NOTE.sub('', text or '').strip()


def _body_text(html: str) -> str:
    m = _BODY.search(html or '')
    return common.text(m.group(1)) if m else ''


def _body_lines(html: str) -> list[str]:
    m = _BODY.search(html or '')
    return common.lines(m.group(1)) if m else []


def parse_detail(html: str, item: dict, board: Board) -> RawReport:
    published, precision = normalize_published(item['published_raw'])
    abstract, toc, note = None, [], None

    if board.body == 'toc':
        toc = [line for line in _body_lines(html) if line]
        note = '요약 없음'
    elif board.body == 'none':
        note = '요약 없음'
    else:
        text = _strip_source_note(_body_text(html))
        # 안내문만 든 회차를 초록으로 세면 결측률이 거짓으로 내려간다.
        if len(text) < 80 and _ATTACH_ONLY.search(text):
            note = '요약 없음'
        elif text:
            abstract = text
        else:
            note = '요약 없음'

    file_m = _FILE.search(html or '')
    return RawReport(
        id=report_id('bok', board.id_prefix + item['native_id']),
        org='bok',
        board=board.id,
        series=board.series,
        title=item['title'],
        authors=[item['dept']] if item.get('dept') else [],
        published=published,
        date_precision=precision,
        landing_url=item['detail_url'],
        file_url=common.absolute(BASE, file_m.group(1)) if file_m else None,
        abstract=abstract,
        toc=toc,
        abstract_note=note,
    )
