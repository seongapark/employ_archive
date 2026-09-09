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
