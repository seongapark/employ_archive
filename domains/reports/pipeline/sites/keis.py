"""한국고용정보원(KEIS) 목록·상세 파서.

KEIS 는 게시판이 두 모양이다(실측 2026-09-10).

- `proj/*/pblc/list.do` — 표. 제목은 `cell-subject` 의 앵커, 상세는
  `goDetail('categoryIdx=131&pubIdx=11363')` 이 여는 `detail.do` 다.
  상세에 목차(`#tab-content1`)와 요약(`#tab-content2`) 탭이 있다.
- `bbs/115/list.do`(인력수급전망) — 접었다 펴는 `dl.toggle-item` 목록이고
  상세 페이지가 없다. 그래서 `detail_in_list` 가 켜져 있다. 초록도 없다.
"""
from __future__ import annotations

import re

from ..boards import Board
from ..models import RawReport, normalize_published, report_id
from . import common

BASE = 'https://www.keis.or.kr'

_GO_DETAIL = re.compile(r"goDetail\('categoryIdx=(\d+)&(?:amp;)?pubIdx=(\d+)'\)")
_SUBJECT = re.compile(r'class="cell-subject"[^>]*>(.*?)</td>', re.S)
_CELL_DATE = re.compile(r'class="cell-date"[^>]*>(.*?)</td>', re.S)
_ANCHOR_TEXT = re.compile(r'<a[^>]*>(.*?)</a>', re.S)
_PREVIEW = re.compile(r'href="(/keis/[^"]*preview\.do\?[^"]*)"')
_DOWNLOAD = re.compile(r'href="(/keis/[^"]*download\.do\?[^"]*)"')
_FIELD = re.compile(r'<dt[^>]*>\s*{}\s*</dt>\s*<dd[^>]*>(.*?)</dd>', re.S)
_H3 = re.compile(r'<h3 class="text-xxl[^"]*"[^>]*>(.*?)</h3>', re.S)
_TAB = re.compile(r'id="tab-content{}"[^>]*>(.*?)(?=<div class="tab-content"|</main>)', re.S)
_TOGGLE_TITLE = re.compile(r'<strong class="title">(.*?)</strong>', re.S)
_TOGGLE_DATE = re.compile(r'<span class="date">(.*?)</span>\s*</span>', re.S)


def list_url(board: Board, page: int) -> str:
    return common.page_url(board, page)


def parse_list(html: str, board: Board) -> list[dict]:
    if board.detail_in_list:
        return _parse_preview_boxes(html, board)
    return _parse_table(html, board)


def _parse_table(html: str, board: Board) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for row in common.rows(html, 'tr'):
        go = _GO_DETAIL.search(row)
        subject = _SUBJECT.search(row)
        if not (go and subject):
            continue
        category_idx, pub_idx = go.group(1), go.group(2)
        if pub_idx in seen:
            continue
        anchor = _ANCHOR_TEXT.search(subject.group(1))
        title = common.text(anchor.group(1) if anchor else subject.group(1))
        date_cell = _CELL_DATE.search(row)
        raw_date = common.find_date(date_cell.group(1)) if date_cell else None
        if not (title and raw_date):
            continue
        preview = _PREVIEW.search(row)
        seen.add(pub_idx)
        # 목록 주소의 디렉터리에 detail.do 가 있다.
        base_dir = board.list_url.rsplit('/', 1)[0] + '/'
        items.append({
            'native_id': pub_idx,
            'detail_url': (f'{base_dir}detail.do?categoryIdx={category_idx}'
                           f'&pubIdx={pub_idx}'),
            'published_raw': raw_date,
            'title': title,
            'file_url': common.absolute(BASE, preview.group(1)) if preview else None,
        })
    return items


def _parse_preview_boxes(html: str, board: Board) -> list[dict]:
    """인력수급전망(bbs/115) — 목록 항목이 곧 상세다.

    항목은 접었다 펴는 `dl.toggle-item` 이고, 펼친 안쪽에 첨부파일 목록이 있다.
    초록은 없다 — 없는 것을 지어내지 않고 비운다. 결측률이 그것을 센다.
    """
    items: list[dict] = []
    seen: set[str] = set()
    for block in re.split(r'(?=<dl class="toggle-item")', html or '')[1:]:
        dl = _DOWNLOAD.search(block)
        if not dl:
            continue
        nid = re.search(board.item_re, dl.group(1))
        if not nid or nid.group(1) in seen:
            continue
        title_m = _TOGGLE_TITLE.search(block)
        title = common.text(title_m.group(1)) if title_m else ''
        date_m = _TOGGLE_DATE.search(block)
        raw_date = common.find_date(date_m.group(1)) if date_m else None
        if not (title and raw_date):
            continue
        preview = _PREVIEW.search(block)
        seen.add(nid.group(1))
        items.append({
            'native_id': nid.group(1),
            'detail_url': board.list_url,
            'published_raw': raw_date,
            'title': title,
            'authors': ['한국고용정보원'],
            'file_url': common.absolute(BASE, preview.group(1)) if preview else None,
            'block': block,
        })
    return items


def parse_detail(html: str, item: dict, board: Board) -> RawReport:
    published, precision = normalize_published(item['published_raw'])
    authors = item.get('authors') or _split(_field(html, '저자'))
    # 탭 안에 스크린리더용 제목(<h3 class="sr-only">목차</h3>)과 '목록' 버튼이
    # 섞여 있다. 그것을 목차 항목으로 실으면 모든 보고서의 목차가 같아 보인다.
    toc = [line for line in common.lines(_tab(html, 1))
           if line not in ('목차', '목록', '요약')]
    abstract = common.text(_tab(html, 2))
    abstract = re.sub(r'^요약\s*', '', abstract).strip() or None
    return RawReport(
        id=report_id('keis', board.id_prefix + item['native_id']),
        org='keis',
        board=board.id,
        series=board.series,
        title=item['title'],
        authors=authors,
        published=published,
        date_precision=precision,
        landing_url=item['detail_url'],
        file_url=item.get('file_url'),
        abstract=abstract,
        toc=toc,
    )


def _field(fragment: str, label: str) -> str:
    m = re.search(_FIELD.pattern.format(re.escape(label)), fragment or '', re.S)
    return common.text(m.group(1)) if m else ''


def _tab(html: str, n: int) -> str:
    m = re.search(_TAB.pattern.format(n), html or '', re.S)
    return m.group(1) if m else ''


def _split(s: str) -> list[str]:
    parts = re.split(r'[,·;/]', s or '')
    return [p.strip() for p in parts if p.strip()]
