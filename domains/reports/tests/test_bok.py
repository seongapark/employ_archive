"""한국은행 파서. 고정본만 읽는다 — 네트워크를 쓰지 않는다."""
from pathlib import Path

import pytest

from domains.reports.pipeline.boards import Board
from domains.reports.pipeline.sites import bok

FIX = Path(__file__).parent / 'fixtures'


def board(**over):
    base = dict(id='bok-note', org='bok', name='BOK 이슈노트', series='BOK 이슈노트',
                list_url='https://www.bok.or.kr/portal/singl/newsData/list.do?menuNo=200433',
                menu_no='200433', item_re=r'nttId=(\d+)', body='abstract')
    base.update(over)
    return Board.model_validate(base)


@pytest.fixture(scope='module')
def list_html():
    return (FIX / 'bok_list.html').read_text(encoding='utf-8')


def test_list_url_carries_the_menu_number_and_page(list_html):
    url = bok.list_url(board(), 3)
    assert 'menuNo=200433' in url
    assert 'pageIndex=3' in url
    assert 'pageUnit=100' in url
    assert 'listCont.do' in url


def test_parse_list_reads_every_row(list_html):
    items = bok.parse_list(list_html, board())
    assert len(items) >= 50
    first = items[0]
    assert first['native_id'].isdigit()
    assert first['detail_url'].startswith('https://www.bok.or.kr/portal/bbs/')
    assert 'nttId=' in first['detail_url']
    assert first['title']
    assert first['published_raw'].startswith('20')


def test_parse_list_keeps_the_department(list_html):
    items = bok.parse_list(list_html, board())
    assert any(i.get('dept') for i in items)


def test_parse_list_does_not_duplicate_ids(list_html):
    items = bok.parse_list(list_html, board())
    ids = [i['native_id'] for i in items]
    assert len(ids) == len(set(ids))
