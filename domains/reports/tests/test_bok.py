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
    # 고정본 100행 전부가 dept 를 가진다(실측). any 는 정규식이 절반쯤
    # 깨져도 통과하는 약한 단언이라 all 로 쓴다.
    assert all(i.get('dept') for i in items)


def test_parse_list_does_not_duplicate_ids(list_html):
    items = bok.parse_list(list_html, board())
    ids = [i['native_id'] for i in items]
    assert len(ids) == len(set(ids))


def _detail(name):
    return (FIX / name).read_text(encoding='utf-8')


def test_abstract_board_puts_the_body_in_the_abstract():
    item = {'native_id': '11064490', 'title': '가구DB를 이용한 가계부채 리스크 평가',
            'detail_url': 'https://www.bok.or.kr/portal/bbs/P0002353/view.do?nttId=11064490',
            'published_raw': '2026.09.07', 'dept': '금융통화연구실'}
    rec = bok.parse_detail(_detail('bok_detail_note.html'), item, board())
    assert rec.id == 'bok-11064490'
    assert rec.org == 'bok'
    assert rec.abstract and len(rec.abstract) > 500
    assert rec.toc == []
    assert rec.abstract_note is None


def test_toc_board_puts_the_body_in_the_toc():
    item = {'native_id': '999001', 'title': '경제전망보고서(2026년 8월)',
            'detail_url': 'https://www.bok.or.kr/portal/bbs/P0002359/view.do?nttId=999001',
            'published_raw': '2026.08.27', 'dept': '조사국'}
    b = board(id='bok-outlook', name='경제전망보고서', series='경제전망보고서',
              menu_no='200066', body='toc')
    rec = bok.parse_detail(_detail('bok_detail_outlook.html'), item, b)
    assert rec.abstract is None
    assert len(rec.toc) >= 3
    assert rec.abstract_note == '요약 없음'


def test_none_board_drops_the_attachment_notice():
    item = {'native_id': '999002', 'title': '2024년 4/4분기 주력산업 모니터링 보고서',
            'detail_url': 'https://www.bok.or.kr/portal/bbs/B0000357/view.do?nttId=999002',
            'published_raw': '2025.02.17', 'dept': '조사국'}
    b = board(id='bok-industry', name='주력산업 모니터링 보고서',
              series='주력산업 모니터링 보고서', menu_no='201127', body='none')
    rec = bok.parse_detail(_detail('bok_detail_industry.html'), item, b)
    assert rec.abstract is None
    assert rec.toc == []
    assert rec.abstract_note == '요약 없음'


def test_the_attachment_url_is_the_stable_one_not_the_expiring_cdn():
    item = {'native_id': '11064490', 'title': 'ㄱ',
            'detail_url': 'https://www.bok.or.kr/portal/bbs/P0002353/view.do?nttId=11064490',
            'published_raw': '2026.09.07', 'dept': ''}
    rec = bok.parse_detail(_detail('bok_detail_note.html'), item, board())
    assert rec.file_url and rec.file_url.startswith('https://www.bok.or.kr/fileSrc/')
    # 뷰어가 쓰는 file-cdn 주소에는 만료 토큰이 붙는다. 저장하면 안 된다.
    assert 'file-cdn' not in rec.file_url
    assert 'token=' not in rec.file_url


def test_the_source_note_prefix_is_stripped_from_an_issue_abstract():
    body = ('* 본 내용은 2026년 5월 경제전망보고서 에 수록된 <중장기 심층연구> 입니다.\n'
            '경 제 전 망 보 고 서 전문 은 아래의 경로에서 확인 가능합니다.\n'
            '실제 초록 문장이 여기서 시작한다. ' + '가' * 300)
    assert bok._strip_source_note(body).startswith('실제 초록 문장이')
