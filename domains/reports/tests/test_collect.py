import json

from domains.reports.pipeline import collect
from domains.reports.pipeline.boards import Board

BOARD = Board(id='kli-research', org='kli', name='연구보고서', series='연구보고서',
              list_url='https://example.org/list',
              page_url='https://example.org/list?p={page}',
              item_re=r'sn=(\d+)')


def items(n, published='2025-05-01'):
    return [{'native_id': str(i), 'detail_url': f'https://example.org/d/{i}',
             'published_raw': published, 'title': f'제목{i}'} for i in range(n)]


def one_page(rows):
    state = {'n': 0}

    def parse(html, board):
        state['n'] += 1
        return rows if state['n'] == 1 else []
    return parse


def stub_detail(html, item, board):
    return collect.stub_record(item, board)


def test_no_network_without_injection(tmp_path, monkeypatch):
    # 주입하면 네트워크가 꺼진다. 이 사실 자체를 테스트가 지킨다.
    monkeypatch.setattr(collect, 'DATA', tmp_path)

    def boom(url, **kw):
        raise AssertionError(f'테스트가 네트워크에 나갔다: {url}')

    assert collect.main(['--dry-run'], collectors={}, fetch=boom) == 0


def test_detail_cap_limits_requests_per_run():
    # 회차당 상세 조회 상한. 게시판 예의는 코드로 강제한다.
    fetched = []

    def fake_fetch(url, **kw):
        fetched.append(url)
        return '<html></html>'

    recs, result = collect.collect_board(
        BOARD, fetch=fake_fetch, throttle=collect.NoThrottle(),
        detail_cap=40, existing=[],
        parse_list=one_page(items(100)), parse_detail=stub_detail)
    assert len([u for u in fetched if '/d/' in u]) == 40
    assert len(recs) == 40


def test_a_board_stops_at_the_cutoff_year():
    rows = [{'native_id': '1', 'detail_url': 'https://x/1',
             'published_raw': '2025-05-01', 'title': 'ㄱ'},
            {'native_id': '2', 'detail_url': 'https://x/2',
             'published_raw': '2020-11-01', 'title': 'ㄴ'}]
    recs, result = collect.collect_board(
        BOARD, fetch=lambda url, **kw: '<html></html>',
        throttle=collect.NoThrottle(), detail_cap=40, existing=[],
        parse_list=one_page(rows), parse_detail=stub_detail)
    assert [r.id for r in recs] == ['kli-1']
    assert result['reached_cutoff'] is True


def test_a_board_that_parses_nothing_is_flagged():
    # 200 인데 항목 0건은 마크업이 바뀌었다는 신호다.
    _, result = collect.collect_board(
        BOARD, fetch=lambda url, **kw: '<html>목록이 아니다</html>',
        throttle=collect.NoThrottle(), detail_cap=40, existing=[],
        parse_list=lambda html, b: [], parse_detail=stub_detail)
    assert result['parsed'] == 0
    assert result['ok'] is False


def test_a_request_failure_is_recorded_not_raised():
    def boom(url, **kw):
        raise RuntimeError('502')

    _, result = collect.collect_board(
        BOARD, fetch=boom, throttle=collect.NoThrottle(), detail_cap=40,
        existing=[], parse_list=one_page(items(3)), parse_detail=stub_detail)
    assert result['ok'] is False and '502' in result['error']


def test_a_board_whose_detail_is_in_the_list_does_not_fetch_details():
    # 인력수급전망이 이 경우다. 상세가 없는데 요청하면 건마다 헛걸음이다.
    board = BOARD.model_copy(update={'detail_in_list': True})
    fetched = []
    rows = items(5)
    for r in rows:
        r['block'] = '<html>본문</html>'
    collect.collect_board(
        board, fetch=lambda url, **kw: fetched.append(url) or '<html></html>',
        throttle=collect.NoThrottle(), detail_cap=40, existing=[],
        parse_list=one_page(rows), parse_detail=stub_detail)
    assert all('/d/' not in u for u in fetched), '상세를 다시 요청했다'


def test_already_known_records_are_not_refetched():
    existing = [collect.stub_record(items(1)[0], BOARD)]
    fetched = []
    collect.collect_board(
        BOARD, fetch=lambda url, **kw: fetched.append(url) or '<html></html>',
        throttle=collect.NoThrottle(), detail_cap=40, existing=existing,
        parse_list=one_page(items(3)), parse_detail=stub_detail)
    assert len([u for u in fetched if '/d/' in u]) == 2


def test_last_run_records_each_board(tmp_path, monkeypatch):
    monkeypatch.setattr(collect, 'DATA', tmp_path)
    collect.write_last_run({'kli-research': {'ok': True, 'parsed': 12, 'added': 3}}, [])
    last = json.loads((tmp_path / 'last_run.json').read_text(encoding='utf-8'))
    assert last['boards']['kli-research']['parsed'] == 12
    assert last['at']


def test_a_partial_run_does_not_erase_other_boards_last_run(tmp_path, monkeypatch):
    # --board/--org 로 게시판 하나만 돌려도 results 에는 그 게시판만 담긴다.
    # write_last_run 이 예전처럼 통째로 덮어쓰면 나머지 게시판의 최근 기록이
    # 사라지고, check_run.py 는 그 게시판들이 돌았는지 아예 알 수 없게 된다.
    monkeypatch.setattr(collect, 'DATA', tmp_path)
    collect.write_last_run(
        {'kli-research': {'ok': True, 'parsed': 12, 'added': 3},
         'keis-issue': {'ok': True, 'parsed': 5, 'added': 1}}, [])
    collect.write_last_run({'kli-research': {'ok': True, 'parsed': 1, 'added': 0}}, [])
    last = json.loads((tmp_path / 'last_run.json').read_text(encoding='utf-8'))
    assert last['boards']['kli-research']['parsed'] == 1, '이번 회차 결과로 갱신돼야 한다'
    assert last['boards']['keis-issue']['parsed'] == 5, '이번 회차에 안 돈 게시판 기록이 지워졌다'


def test_last_run_drops_boards_no_longer_registered(tmp_path, monkeypatch):
    # boards.json 에서 지워진 게시판의 낡은 키는 계속 남아 있으면 안 된다.
    monkeypatch.setattr(collect, 'DATA', tmp_path)
    collect.write_last_run({'no-longer-a-board': {'ok': True, 'parsed': 1, 'added': 0}}, [])
    collect.write_last_run({'kli-research': {'ok': True, 'parsed': 2, 'added': 0}}, [])
    last = json.loads((tmp_path / 'last_run.json').read_text(encoding='utf-8'))
    assert 'no-longer-a-board' not in last['boards']
    assert last['boards']['kli-research']['parsed'] == 2


def test_an_undated_old_item_is_skipped_not_failed():
    # 목록에 날짜가 없는 줄(고정 공지 등)은 위쪽 cutoff 검사를 지나친다.
    # 상세를 열어야 옛 글인 게 드러나는데, 그때 RawReport 검증 예외가 게시판
    # 전체를 죽이면 그날 그 게시판 수집이 통째로 버려진다 — 2026-09-13 에
    # kdi-focus 가 2009-03-31 공지 하나로 그렇게 실패했다.
    rows = [{'native_id': '1', 'detail_url': 'https://x/1',
             'published_raw': '2025-05-01', 'title': 'ㄱ'},
            {'native_id': '9', 'detail_url': 'https://x/9', 'title': '공지'}]

    def detail(html, item, board):
        if item['native_id'] == '9':
            item = dict(item, published_raw='2009-03-31')
        return collect.stub_record(item, board)

    recs, result = collect.collect_board(
        BOARD, fetch=lambda url, **kw: '<html></html>',
        throttle=collect.NoThrottle(), detail_cap=40, existing=[],
        parse_list=one_page(rows), parse_detail=detail)

    assert result['ok'] is True and result['error'] is None
    assert [r.id for r in recs] == ['kli-1']
    assert result['skipped_old'] == 1


def test_a_broken_parser_still_fails_the_board():
    # 컷오프만 봐준다. 제목이 비는 것 같은 진짜 파서 고장까지 삼키면
    # 이 가드가 지키려던 것을 잃는다.
    rows = [{'native_id': '1', 'detail_url': 'https://x/1',
             'published_raw': '2025-05-01', 'title': 'ㄱ'}]

    def detail(html, item, board):
        return collect.stub_record(dict(item, published_raw='깨진 날짜'), board)

    _, result = collect.collect_board(
        BOARD, fetch=lambda url, **kw: '<html></html>',
        throttle=collect.NoThrottle(), detail_cap=40, existing=[],
        parse_list=one_page(rows), parse_detail=detail)
    assert result['ok'] is False and result['error']


def _pages(pages):
    """쪽 번호대로 목록을 돌려주는 parse_list. 몇 쪽을 읽었는지 센다."""
    state = {'read': 0}

    def parse(html, board):
        state['read'] += 1
        idx = state['read'] - 1
        return pages[idx] if idx < len(pages) else []
    return parse, state


def test_a_page_of_only_known_items_stops_the_paging():
    """평소 회차는 한 쪽만 읽는다 — 컷오프까지 다시 훑지 않는다."""
    rows = items(10)
    existing = [collect.stub_record(it, BOARD) for it in rows]
    parse, state = _pages([rows, items(10)])

    recs, result = collect.collect_board(
        BOARD, fetch=lambda url, **kw: '<html></html>',
        throttle=collect.NoThrottle(), detail_cap=40, existing=existing,
        parse_list=parse, parse_detail=stub_detail)

    assert state['read'] == 1
    assert recs == []
    assert result['ok'] is True
    assert result['parsed'] == 10


def test_paging_follows_a_backlog_past_the_first_page():
    """밀린 신규는 쪽을 넘어가며 따라잡는다. 앞 N건 고정이면 놓친다.

    1쪽은 전부 신규(밀린 것), 2쪽은 신규가 한 건 섞여 있고, 3쪽은 전부 아는
    것이다. 3쪽에서 멈추되 2쪽의 그 한 건은 담아야 한다.
    """
    쪽1 = items(10)
    쪽2 = [dict(it, native_id=f'2-{it["native_id"]}',
                detail_url=f'https://example.org/d/2-{it["native_id"]}')
           for it in items(10)]
    쪽3 = [dict(it, native_id=f'3-{it["native_id"]}',
                detail_url=f'https://example.org/d/3-{it["native_id"]}')
           for it in items(10)]
    existing = [collect.stub_record(it, BOARD) for it in 쪽2[1:] + 쪽3]
    parse, state = _pages([쪽1, 쪽2, 쪽3])

    recs, result = collect.collect_board(
        BOARD, fetch=lambda url, **kw: '<html></html>',
        throttle=collect.NoThrottle(), detail_cap=40, existing=existing,
        parse_list=parse, parse_detail=stub_detail)

    assert state['read'] == 3
    assert len(recs) == 11
    assert result['parsed'] == 30
