"""한국개발연구원(KDI) 목록·상세 파서.

KDI 는 한 게시판 안에 성격이 다른 문서가 섞인다 — 기타보고서 게시판에는
예비타당성조사·타당성 재조사 보고서가 함께 올라온다(실측 5종). 그래서
boards.json 의 `category_keep` 으로 분류(`b.i15`)를 걸러낸다.

목록에 발간일이 없다. 상세의 `<span class="date">` 에서 읽는다.
상세는 `bundlebox desc sumy01`(국문요약) · `sumy02`(목차) 로 나뉜다.
"""
from __future__ import annotations

import re

from ..boards import Board
from ..models import RawReport, normalize_published, report_id
from . import common

BASE = 'https://www.kdi.re.kr/research/'

_CATEGORY = re.compile(r'<b[^>]*class="i15"[^>]*>(.*?)</b>', re.S)
_TITLE = re.compile(r'<strong>(.*?)</strong>', re.S)
_PAGES = re.compile(r'<span>\s*(\d+)\s*p\s*</span>')
_FILE = re.compile(r"location\.href='(/file/download\?[^']+)'")
# 묶음을 클래스 접미사(sumy01/02)로 고르면 그게 없는 페이지에서 통째로 놓친다
# — 경제동향이 그랬다. <dt> 에 적힌 이름으로 고른다.
_BUNDLE = re.compile(
    r'<div class="bundlebox desc[^"]*">\s*<dl>\s*<dt>\s*([^<]{1,20}?)\s*<', re.S)
_BUNDLE_BODY = re.compile(r'<dd>(.*?)</dd>', re.S)
_EDITOR = re.compile(r'<div class="editor-template">(.*?)</div>', re.S)
_DETAIL_DATE = re.compile(r'<span class="date">(.*?)</span>', re.S)
_AUTHOR_LIST = re.compile(r'<div class="page_author-list">(.*?)</div>\s*<div', re.S)
# 경제동향은 항목이 앵커가 아니라 월 버튼이다.
#   <button onclick="location.href='/research/monTrends?pub_no=18567'">1월</button>
_BUTTON_ITEM = re.compile(
    r"location\.href='(/research/[^']*?(\d+))'[^>]*>\s*([^<]{1,12}?)\s*</button>")
_PAGE_YEAR = re.compile(r"var\s+year\s*=\s*'(\d{4})'")
_META_DESC = re.compile(r'<meta name="description" content="(.*?)"', re.S)
_AUTHOR = re.compile(r'<strong>\s*([^<]{2,20}?)\s*(?:<span>.*?</span>)?\s*</strong>', re.S)


def list_url(board: Board, page: int) -> str:
    return common.page_url(board, page)


def parse_list(html: str, board: Board) -> list[dict]:
    if board.list_style == 'buttons':
        return _parse_buttons(html, board)
    items: list[dict] = []
    seen: set[str] = set()
    plain = (html or '').replace('&amp;', '&')
    for block in re.split(r'(?=<li[\s>])', plain)[1:]:
        m = re.search(board.item_re, block)
        if not m:
            continue
        native_id = m.group(1)
        if native_id in seen:
            continue
        cat_m = _CATEGORY.search(block)
        category = common.text(cat_m.group(1)) if cat_m else None
        if board.category_keep and category != board.category_keep:
            continue
        href_m = re.search(r'href="([^"]*' + board.item_re + r'[^"]*)"', block)
        title_m = _TITLE.search(block)
        if not (href_m and title_m):
            continue
        title = common.text(title_m.group(1))
        if not title:
            continue
        pages_m = _PAGES.search(block)
        file_m = _FILE.search(block)
        seen.add(native_id)
        items.append({
            'native_id': native_id,
            'detail_url': common.absolute(BASE, href_m.group(1)),
            'published_raw': common.find_date(block),
            'title': title,
            'category': category,
            'pages': int(pages_m.group(1)) if pages_m else None,
            'file_url': (common.absolute('https://www.kdi.re.kr/', file_m.group(1))
                         if file_m else None),
        })
    return items


def parse_detail(html: str, item: dict, board: Board) -> RawReport:
    raw_date = item.get('published_raw')
    if not raw_date:
        date_m = _DETAIL_DATE.search(html or '')
        raw_date = common.find_date(date_m.group(1)) if date_m else None
    if not raw_date:
        raw_date = common.find_date(html or '')
    published, precision = normalize_published(raw_date or '')

    abstract, toc = None, []
    for m in _BUNDLE.finditer(html or ''):
        label = common.text(m.group(1))
        body_m = _BUNDLE_BODY.search(html, m.end())
        if not body_m:
            continue
        editor = _EDITOR.search(body_m.group(1))
        chunk = editor.group(1) if editor else body_m.group(1)
        # 라벨이 '국문 목차'처럼 띄어 쓰이기도 한다. 영문판은 담지 않는다.
        flat = label.replace(' ', '')
        if flat in ('국문요약', '요약', '초록') and abstract is None:
            abstract = common.text(chunk) or None
        elif '목차' in flat and '영문' not in flat and not toc:
            toc = common.lines(chunk)
    if abstract is None:
        # 경제동향은 요약 묶음이 없다. 페이지가 meta description 에 그달 요지를
        # 그대로 싣는다 — 지어내는 게 아니라 기관이 쓴 문장이다.
        meta = _META_DESC.search(html or '')
        if meta:
            abstract = common.text(meta.group(1)) or None
    return RawReport(
        id=report_id('kdi', board.id_prefix + item['native_id']),
        org='kdi',
        board=board.id,
        series=board.series,
        title=item['title'],
        authors=_authors(html),
        published=published,
        date_precision=precision,
        pages=item.get('pages'),
        landing_url=item['detail_url'],
        file_url=item.get('file_url'),
        abstract=abstract,
        toc=toc,
    )


def _authors(html: str) -> list[str]:
    block = _AUTHOR_LIST.search(html or '')
    if not block:
        return []
    return [common.text(n) for n in _AUTHOR.findall(block.group(1)) if common.text(n)]


def _parse_buttons(html: str, board: Board) -> list[dict]:
    """경제동향 — 한 해 페이지에 월 버튼 열둘이 놓인다.

    버튼 글자는 '1월' 이라 그것만으로는 제목이 안 된다. 페이지가 들고 있는
    연도(`var year = '2025'`)와 붙여 '경제동향 2025년 1월' 로 만든다.
    """
    plain = (html or '').replace('&amp;', '&')
    year_m = _PAGE_YEAR.search(plain)
    if not year_m:
        return []
    year = year_m.group(1)
    items: list[dict] = []
    seen: set[str] = set()
    for href, native_id, label in _BUTTON_ITEM.findall(plain):
        if not re.search(board.item_re, href) or native_id in seen:
            continue
        month = re.match(r'(\d{1,2})\s*월', label)
        if not month:
            continue
        seen.add(native_id)
        items.append({
            'native_id': native_id,
            'detail_url': common.absolute('https://www.kdi.re.kr/', href),
            'published_raw': f'{year}.{month.group(1)}',
            'title': f'{board.series} {year}년 {month.group(1)}월',
            'category': None,
            'pages': None,
            'file_url': None,
        })
    return items
