from domains.reports.pipeline import boards


def test_every_board_has_the_fields_the_collector_needs():
    for b in boards.load_boards():
        assert b.id and b.org and b.series and b.list_url
        assert b.item_re, f'{b.id}: 상세 링크 패턴이 없다'


def test_board_ids_are_unique():
    ids = [b.id for b in boards.load_boards()]
    assert len(ids) == len(set(ids))


def test_all_five_orgs_are_present():
    orgs = {b.org for b in boards.load_boards()}
    assert orgs == {'kli', 'keis', 'kdi', 'kiet', 'bok'}


def test_the_filter_field_is_gone_from_the_board_model():
    # 취지가 바뀌어 게시판이 레코드를 거르지 않는다. 필드가 되살아나면
    # 거르는 코드도 같이 돌아온다 — 그때 여기서 걸려야 한다.
    assert 'filter' not in boards.Board.model_fields


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


def test_every_bok_board_is_registered_with_a_menu_number_and_body_kind():
    bok_boards = {b.id: b for b in boards.load_boards() if b.org == 'bok'}
    assert set(bok_boards) == {
        'bok-outlook', 'bok-assess', 'bok-region', 'bok-industry',
        'bok-note', 'bok-issue', 'bok-intl', 'bok-research'}
    for b in bok_boards.values():
        assert b.menu_no and b.menu_no.isdigit()
        assert b.body in ('abstract', 'toc', 'none')


def test_bok_board_ids_do_not_collide_with_other_orgs():
    ids = [b.id for b in boards.load_boards()]
    assert len(ids) == len(set(ids))
