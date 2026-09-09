"""한국노동연구원(KLI) 목록·상세 파서.

이 모듈은 KLI 의 HTML 만 안다. 저장도 판정도 하지 않는다 — 그래야 KLI 가
사이트를 개편해도 나머지 세 기관이 계속 돈다.

목록은 `aria-label` 이 붙은 표다(번호·구분·서명·저자·출판일·첨부파일·원문).
상세는 `<p class="ti_st1">제목</p><div class="cont">본문</div>` 묶음이 이어진다.
"""
from __future__ import annotations

import re

from ..boards import Board
from ..models import RawReport, normalize_published, report_id
from . import common

BASE = 'https://www.kli.re.kr'

_TITLE = re.compile(
    r'aria-label="제목"[^>]*>\s*<a href="([^"]*)"[^>]*>(.*?)</a>', re.S)
_AUTHORS = re.compile(r'aria-label="저자"[^>]*>(.*?)</td>', re.S)
_PUBLISHED = re.compile(r'aria-label="출판일"[^>]*>(.*?)</td>', re.S)
_FILE = re.compile(r'href="(/kliFileDownload\?[^"]*)"')
_SECTION = re.compile(
    r'<p class="ti_st1">\s*(.*?)\s*</p>\s*<div class="cont">(.*?)</div>', re.S)

# 상세의 어느 묶음을 초록으로 볼 것인가. KLI 는 보고서 종류마다 이름이 다르다.
_ABSTRACT_LABELS = ('국문요약', '요약', '초록', '내용', '주요내용')


def list_url(board: Board, page: int) -> str:
    if board.single_page and page > 1:
        return ''
    return common.page_url(board, page)


def parse_list(html: str, board: Board) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for row in common.rows(html, 'tr'):
        m = _TITLE.search(row)
        if not m:
            continue
        href, title = m.group(1), common.text(m.group(2))
        nid = re.search(board.item_re, href)
        if not (nid and title):
            continue
        native_id = nid.group(1)
        if native_id in seen:
            continue
        published = _PUBLISHED.search(row)
        raw_date = common.find_date(published.group(1)) if published else None
        if not raw_date:
            continue
        authors = _AUTHORS.search(row)
        file_m = _FILE.search(row)
        seen.add(native_id)
        items.append({
            'native_id': native_id,
            'detail_url': common.absolute(BASE, href),
            'published_raw': raw_date,
            'title': title,
            'authors': _split_authors(common.text(authors.group(1)) if authors else ''),
            'file_url': common.absolute(BASE, file_m.group(1)) if file_m else None,
        })
    return items


def parse_detail(html: str, item: dict, board: Board) -> RawReport:
    published, precision = normalize_published(item['published_raw'])
    abstract, toc = None, []
    for label, body in _SECTION.findall(html or ''):
        name = common.text(label)
        if name == '목차' and not toc:
            toc = common.lines(body)
        elif name in _ABSTRACT_LABELS and not abstract:
            abstract = common.text(body) or None
    return RawReport(
        id=report_id(board.org, board.id_prefix + item['native_id']),
        org='kli',
        board=board.id,
        series=board.series,
        title=item['title'],
        authors=item.get('authors') or [],
        published=published,
        date_precision=precision,
        landing_url=item['detail_url'],
        file_url=item.get('file_url'),
        abstract=abstract,
        toc=toc,
    )


def _split_authors(s: str) -> list[str]:
    parts = re.split(r'[,·;/]| 외 ', s or '')
    return [p.strip() for p in parts if p.strip()]
