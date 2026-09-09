from domains.reports.pipeline import check_run


def last(boards, **extra):
    payload = {'at': '2026-09-10T11:30:00+09:00', 'boards': boards,
               'unregistered': []}
    payload.update(extra)
    return payload


def test_a_quiet_board_passes():
    # 고용영향평가브리프처럼 몇 달씩 안 올라오는 게 정상인 게시판이 있다.
    code, msgs = check_run.check(last({
        'kli-eia': {'ok': True, 'parsed': 8, 'added': 0},
    }))
    assert code == 0
    assert any('신규 없음' in m for m in msgs)


def test_a_request_failure_fails_the_run():
    code, msgs = check_run.check(last({
        'kdi-report': {'ok': False, 'parsed': 0, 'added': 0, 'error': '502'},
    }))
    assert code == 1
    assert any('kdi-report' in m for m in msgs)


def test_parsing_nothing_from_a_served_page_fails_the_run():
    code, _ = check_run.check(last({
        'kiet-report': {'ok': False, 'parsed': 0, 'added': 0,
                        'error': '목록을 받았지만 항목이 0건이다 — 마크업 변경 신호'},
    }))
    assert code == 1


def test_known_down_lets_a_named_board_through_until_its_deadline():
    code, _ = check_run.check(
        last({'kdi-report': {'ok': False, 'parsed': 0, 'added': 0, 'error': '502'}}),
        known_down='kdi-report@2026-09-30', today='2026-09-10')
    assert code == 0


def test_known_down_fails_once_the_deadline_passes():
    code, msgs = check_run.check(
        last({'kdi-report': {'ok': False, 'parsed': 0, 'added': 0, 'error': '502'}}),
        known_down='kdi-report@2026-09-30', today='2026-10-01')
    assert code == 1
    assert any('기한' in m for m in msgs)


def test_known_down_fails_when_the_board_comes_back():
    # 알람이지 스위치가 아니다. 되살아나면 일부러 실패시켜 지우게 만든다.
    code, msgs = check_run.check(
        last({'kdi-report': {'ok': True, 'parsed': 30, 'added': 2}}),
        known_down='kdi-report@2026-09-30', today='2026-09-10')
    assert code == 1
    assert any('되살아났다' in m for m in msgs)


def test_unregistered_boards_warn_but_do_not_fail():
    payload = last({'kli-research': {'ok': True, 'parsed': 10, 'added': 1}})
    payload['unregistered'] = ['/menu.es?mid=a10109990000']
    code, msgs = check_run.check(payload)
    assert code == 0
    assert any('미등록' in m for m in msgs)


def test_high_abstract_miss_rate_warns_but_does_not_fail():
    payload = last({'kli-research': {'ok': True, 'parsed': 10, 'added': 1}},
                   abstract_missing={'keis': {'인력수급전망':
                                              {'total': 20, 'missing': 18, 'rate': 0.9}}})
    code, msgs = check_run.check(payload)
    assert code == 0
    assert any('결측률 높음' in m for m in msgs)


def test_a_run_with_no_boards_at_all_is_reported():
    code, msgs = check_run.check(last({}))
    assert any('수집한 게시판이 없다' in m for m in msgs)
