from domains.reports.pipeline import boards


def test_every_board_has_the_fields_the_collector_needs():
    for b in boards.load_boards():
        assert b.id and b.org and b.series and b.list_url
        assert b.item_re, f'{b.id}: 상세 링크 패턴이 없다'


def test_board_ids_are_unique():
    ids = [b.id for b in boards.load_boards()]
    assert len(ids) == len(set(ids))


def test_only_kdi_and_kiet_boards_are_filtered():
    # KLI·KEIS 는 기관 전체가 고용·노동이라 거르지 않는다(스펙 §5-2).
    for b in boards.load_boards():
        if b.filter:
            assert b.org in ('kdi', 'kiet'), f'{b.id} 에 필터가 켜져 있다'


def test_all_four_orgs_are_present():
    orgs = {b.org for b in boards.load_boards()}
    assert orgs == {'kli', 'keis', 'kdi', 'kiet'}


def test_only_the_boards_without_a_detail_page_read_it_from_the_list():
    # 실측(2026-09-10): KEIS proj 게시판은 detail.do 상세가 따로 있고, 인력수급전망
    # (bbs/115)만 목록이 곧 상세다. 이 플래그가 잘못 켜지면 초록이 통째로 비고,
    # 잘못 꺼지면 없는 상세를 건마다 한 번씩 더 요청한다.
    flagged = {b.id for b in boards.load_boards() if b.detail_in_list}
    assert flagged == {'keis-supply'}


def test_unregistered_board_is_reported_not_added():
    known = [boards.Board(
        id='kli-research', org='kli', name='연구보고서', series='연구보고서',
        list_url='https://www.kli.re.kr/menu.es?mid=a10102060000',
        item_re=r'pblct_sn=(\d+)',
    )]
    html = '''
      <a href="/menu.es?mid=a10102060000">연구보고서</a>
      <a href="/menu.es?mid=a10109990000">새로 생긴 게시판</a>
    '''
    found = boards.unregistered(html, 'kli', known)
    assert found == ['/menu.es?mid=a10109990000']


def test_a_registered_board_is_not_reported():
    known = [boards.Board(
        id='kli-research', org='kli', name='연구보고서', series='연구보고서',
        list_url='https://www.kli.re.kr/menu.es?mid=a10102060000',
        item_re=r'pblct_sn=(\d+)',
    )]
    html = '<a href="/menu.es?mid=a10102060000">연구보고서</a>'
    assert boards.unregistered(html, 'kli', known) == []
