"""네 기관 파서. 픽스처는 2026-09-10 에 받은 실제 페이지다.

테스트는 두 겹이다.
1. 픽스처 내용을 몰라도 성립하는 불변식 — 필드가 제자리에 있는지.
2. 눈으로 본 값을 그대로 박은 것 — 제목 자리에 저자가 들어가도 1번은 통과하므로.
"""
from pathlib import Path

import pytest

from domains.reports.pipeline import boards
from domains.reports.pipeline.models import normalize_published
from domains.reports.pipeline.sites import kdi, keis, kiet, kli

FIX = Path(__file__).parent / 'fixtures'
BOARDS = {b.id: b for b in boards.load_boards()}


def fixture(name: str) -> str:
    return (FIX / name).read_bytes().decode('utf-8', 'replace')


# 파서 · 게시판 · 목록 픽스처
CASES = [
    (kli, 'kli-research', 'kli_list.html'),
    (keis, 'keis-research', 'keis_list.html'),
    (keis, 'keis-supply', 'keis_supply_list.html'),
    (kiet, 'kiet-report', 'kiet_report_list.html'),
    (kdi, 'kdi-report', 'kdi_report_list.html'),
    (kiet, 'kiet-economy', 'kiet_economy_list.html'),
]


@pytest.mark.parametrize('site,board_id,fx', CASES)
def test_list_yields_items(site, board_id, fx):
    items = site.parse_list(fixture(fx), BOARDS[board_id])
    assert len(items) >= 5, f'{board_id}: 한 페이지에서 5건도 안 잡히면 셀렉터가 틀렸다'


@pytest.mark.parametrize('site,board_id,fx', CASES)
def test_every_item_has_the_fields_the_collector_needs(site, board_id, fx):
    for item in site.parse_list(fixture(fx), BOARDS[board_id]):
        assert item['native_id'].isdigit(), board_id
        assert item['detail_url'].startswith('https://'), board_id
        assert len(item['title'].strip()) >= 4, (board_id, item['title'])
        if item.get('published_raw'):
            assert normalize_published(item['published_raw'])[0] >= '2000-01-01'


@pytest.mark.parametrize('site,board_id,fx', CASES)
def test_titles_are_not_html_fragments(site, board_id, fx):
    # 잘못된 셀렉터는 태그째 잡아 온다. 그러면 검색도 화면도 망가진다.
    for item in site.parse_list(fixture(fx), BOARDS[board_id]):
        assert '<' not in item['title'] and '&lt;' not in item['title']


@pytest.mark.parametrize('site,board_id,fx', CASES)
def test_native_ids_are_unique_on_a_page(site, board_id, fx):
    ids = [i['native_id'] for i in site.parse_list(fixture(fx), BOARDS[board_id])]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize('site,board_id,fx', CASES)
def test_empty_page_yields_nothing_and_does_not_raise(site, board_id, fx):
    # 파싱 0건은 check_run 이 실패로 올린다. 파서는 조용히 빈 목록을 준다.
    assert site.parse_list('<html><body><p>자료가 없습니다</p></body></html>',
                           BOARDS[board_id]) == []


@pytest.mark.parametrize('site,board_id', [
    (kli, 'kli-research'), (keis, 'keis-research'),
    (kiet, 'kiet-report'), (kdi, 'kdi-report'),
])
def test_page_url_advances(site, board_id):
    b = BOARDS[board_id]
    assert site.list_url(b, 1) != site.list_url(b, 2)
    assert site.list_url(b, 2)


# ---------------------------------------------------------------- 실측 못박기

def test_kli_first_item_matches_the_fixture():
    first = kli.parse_list(fixture('kli_list.html'), BOARDS['kli-research'])[0]
    assert first['native_id'] == '10299'
    assert first['title'] == 'KLI Annual Report 2025'
    assert first['published_raw'] == '2026.08.31'
    assert first['authors'] == ['한국노동연구원']


def test_kli_detail_reads_the_table_of_contents():
    items = kli.parse_list(fixture('kli_list.html'), BOARDS['kli-research'])
    rec = kli.parse_detail(fixture('kli_detail.html'), items[0], BOARDS['kli-research'])
    assert rec.id == 'kli-10299'
    assert rec.published == '2026-08-31' and rec.date_precision == 'day'
    assert rec.toc and rec.toc[0].startswith('Foreword')
    assert rec.file_url and rec.file_url.startswith('https://www.kli.re.kr/')


def test_keis_first_item_matches_the_fixture():
    first = keis.parse_list(fixture('keis_list.html'), BOARDS['keis-research'])[0]
    assert first['native_id'] == '11363'
    assert first['title'] == '국민연금과 고령자의 근로활동에 대한 연구'
    assert 'detail.do?categoryIdx=131&pubIdx=11363' in first['detail_url']


def test_keis_detail_reads_the_summary_tab_not_the_toc_tab():
    items = keis.parse_list(fixture('keis_list.html'), BOARDS['keis-research'])
    rec = keis.parse_detail(fixture('keis_detail.html'), items[0],
                            BOARDS['keis-research'])
    assert rec.authors == ['지은정']
    assert rec.abstract and 'OECD' in rec.abstract
    assert '목차' not in rec.toc, '스크린리더용 제목이 목차 항목으로 실렸다'
    assert any('서론' in line for line in rec.toc)


def test_keis_supply_board_reads_the_toggle_list():
    items = keis.parse_list(fixture('keis_supply_list.html'), BOARDS['keis-supply'])
    assert items[0]['title'] == '2026 상반기 주요 업종별 일자리전망'
    assert items[0]['published_raw'] == '2026.02.25'


def test_kiet_first_item_matches_the_fixture():
    first = kiet.parse_list(fixture('kiet_report_list.html'), BOARDS['kiet-report'])[0]
    assert first['native_id'] == '1154'
    assert first['title'] == '한국의 산업정책사'
    assert first['published_raw'] == '2026.03.25'


def test_kiet_detail_takes_the_open_tab_as_the_summary():
    # 버튼 순서(요약·목차)와 본문 순서(목차·요약)가 반대다. 순서로 고르면 뒤집힌다.
    items = kiet.parse_list(fixture('kiet_report_list.html'), BOARDS['kiet-report'])
    rec = kiet.parse_detail(fixture('kiet_detail.html'), items[0],
                            BOARDS['kiet-report'])
    assert rec.abstract and rec.abstract.startswith('대한민국의 현재 산업구조')
    assert rec.toc[:2] == ['발간사', '머리말']


def test_kdi_first_item_matches_the_fixture():
    first = kdi.parse_list(fixture('kdi_report_list.html'), BOARDS['kdi-report'])[0]
    assert first['native_id'] == '19257'
    assert first['title'] == '불평등에 관한 연구: 소득과 자산을 중심으로'
    assert first['pages'] == 77


def test_kdi_etc_board_keeps_only_the_kept_category():
    html = fixture('kdi_etc_list.html')
    assert '예비타당성조사보고서' in html, '픽스처에 버릴 것이 없으면 이 테스트는 무의미하다'
    items = kdi.parse_list(html, BOARDS['kdi-etc'])
    assert items, '기타보고서가 하나도 안 잡혔다'
    assert all(i['category'] == '기타보고서' for i in items)


def test_kdi_detail_fills_date_author_and_abstract():
    items = kdi.parse_list(fixture('kdi_report_list.html'), BOARDS['kdi-report'])
    rec = kdi.parse_detail(fixture('kdi_detail.html'), items[0], BOARDS['kdi-report'])
    assert rec.published == '2026-05-13'      # 목록엔 없고 상세에만 있다
    assert rec.authors == ['이승희']
    assert rec.abstract and rec.abstract.startswith('경제적 불평등은')
    assert rec.toc[:2] == ['발간사', '요약']


def test_kdi_trends_pages_by_year_not_by_number():
    b = BOARDS['kdi-trends']
    assert 'year=2026' in kdi.list_url(b, 1)
    assert 'year=2021' in kdi.list_url(b, 6)
    assert kdi.list_url(b, 7) == '', '연도 목록을 넘어가면 빈 주소여야 멈춘다'


def test_kiet_monthly_articles_are_individual_items_not_issues():
    # 월간지가 호 단위였다면 한 페이지에 12건 이하로만 나온다.
    items = kiet.parse_list(fixture('kiet_economy_list.html'), BOARDS['kiet-economy'])
    assert len(items) >= 20
    assert items[0]['detail_url'].startswith(
        'https://www.kiet.re.kr/research/economyDetailView')


def test_kiet_title_survives_a_classification_tag_before_the_anchor():
    # rpt_tit 안에 <span class="clsf">특집</span> 이 끼어 있다. 앵커가 바로
    # 뒤에 온다고 가정하면 이 게시판만 조용히 0건이 된다(실제로 그랬다).
    html = fixture('kiet_economy_list.html')
    assert 'clsf' in html, '픽스처에 분류 딱지가 없으면 이 테스트는 무의미하다'
    assert kiet.parse_list(html, BOARDS['kiet-economy'])
