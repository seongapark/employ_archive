"""산업연구원(KIET) 목록·상세 파서.

목록은 `li.item` 이고 `div.rpt_tit` 안에 제목·저자·발간일이 다 있다.
상세는 탭 둘로 나뉘는데, **펼쳐진 쪽(`open`)이 요약이고 나머지가 목차**다.
버튼 순서(요약·목차)와 본문 순서(목차·요약)가 반대라 여기서 헷갈리기 쉽다.
"""
from __future__ import annotations

import re

from ..boards import Board
from ..models import RawReport, normalize_published, report_id
from . import common

BASE = 'https://www.kiet.re.kr/research/'

# 제목 앵커 앞에 분류 딱지가 끼는 게시판이 있다(월간 산업경제의 `특집`).
# 앵커가 바로 뒤에 온다고 가정하면 그 게시판만 조용히 0건이 된다.
_ITEM_TITLE = re.compile(
    r'<div class="rpt_tit">(?:(?!</div>).)*?<a href="([^"]+)"[^>]*>\s*<strong>(.*?)</strong>',
    re.S)
_ITEM_META = re.compile(r'<p>(.*?)</p>', re.S)
_DATE_SPAN = re.compile(r'<span class="date">(.*?)</span>', re.S)
_TAB_BOX = re.compile(r'<div class="tab_box([^"]*)"[^>]*>(.*?)</div>', re.S)
_AUTHORS = re.compile(r'<p class="author_list">(.*?)</p>', re.S)


def list_url(board: Board, page: int) -> str:
    return common.page_url(board, page)


def parse_list(html: str, board: Board) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for block in re.split(r'(?=<li class="item")', html or '')[1:]:
        m = _ITEM_TITLE.search(block)
        if not m:
            continue
        href, title = m.group(1), common.text(m.group(2))
        nid = re.search(board.item_re, href.replace('&amp;', '&'))
        if not (nid and title) or nid.group(1) in seen:
            continue
        meta = _ITEM_META.search(block)
        meta_html = meta.group(1) if meta else ''
        date_m = _DATE_SPAN.search(meta_html)
        raw_date = common.find_date(date_m.group(1)) if date_m else None
        if not raw_date:
            continue
        authors = common.text(_DATE_SPAN.sub(' ', meta_html))
        seen.add(nid.group(1))
        items.append({
            'native_id': nid.group(1),
            'detail_url': common.absolute(BASE, href),
            'published_raw': raw_date,
            'title': title,
            'authors': _split(authors),
        })
    return items


def parse_detail(html: str, item: dict, board: Board) -> RawReport:
    published, precision = normalize_published(item['published_raw'])
    abstract, toc = None, []
    for classes, body in _TAB_BOX.findall(html or ''):
        # 펼쳐진 탭이 요약이다. 순서로 고르면 게시판마다 뒤집힌다.
        if 'open' in classes:
            abstract = common.text(body) or None
        elif not toc:
            toc = common.lines(body)
    authors = item.get('authors') or []
    if not authors:
        m = _AUTHORS.search(html or '')
        authors = _split(common.text(m.group(1))) if m else []
    return RawReport(
        id=report_id('kiet', board.id_prefix + item['native_id']),
        org='kiet',
        board=board.id,
        series=board.series,
        title=item['title'],
        authors=authors,
        published=published,
        date_precision=precision,
        landing_url=item['detail_url'],
        file_url=None,      # 원문은 자바스크립트 토큰이라 링크로 만들 수 없다
        abstract=abstract,
        toc=toc,
    )


def _split(s: str) -> list[str]:
    parts = re.split(r'[,·;/]|\s외\s', s or '')
    return [p.strip() for p in parts if p.strip()]
