import json

import pytest

from domains.press.pipeline import collect as c
from domains.press.pipeline import fetch_release as fr


def item(title, desc='', pub='Mon, 07 Sep 2026 12:00:00 +0900',
         link='https://n.news.naver.com/1', orig='https://www.yna.co.kr/view/1'):
    return {'title': title, 'description': desc, 'pubDate': pub,
            'link': link, 'originallink': orig}


def test_window_regular_is_the_release_day_and_the_next():
    a, b, kind = c.window_of('2026-09-07', follow=False)
    assert kind == 'regular'
    assert (a.strftime('%m.%d'), b.strftime('%m.%d')) == ('09.07', '09.08')


def test_window_follow_runs_three_weeks_from_the_release():
    # 정기(D~D+1)와 합쳐 배포일부터 3주다 — 화면이 그렇게 말한다.
    a, b, kind = c.window_of('2026-09-07', follow=True)
    assert kind == 'follow'
    assert (a.strftime('%m.%d'), b.strftime('%m.%d')) == ('09.08', '09.28')


def test_regular_net_is_wide_because_the_release_day_already_filters():
    assert c.relevant('고용보험 가입자 27만8천명 증가', '')
    assert c.relevant('실업급여 환수 통보', '구직급여 반환')
    assert not c.relevant('교보생명 체육대회 개막', '기업 소식')


def test_follow_net_demands_more_than_a_single_word():
    # 2주 구간에는 일반 고용노동 기사가 대량으로 섞인다. '구직급여' 한 낱말로는
    # 제도 논쟁 기사가 전부 들어온다 — 실측에서 그 85건 중 인용은 0건이었다.
    assert not c.relevant_follow('청년 자발적 실업급여 추진 시끌', '구직급여 확대', set())
    assert c.relevant_follow('고용보험 가입자 27만명 증가', '', set())
    assert c.relevant_follow('제조업 고용 회복', '고용행정 통계로 본 노동시장 동향', set())
    assert c.relevant_follow('제조업 15개월 만에 반등', '고용 회복', {'15'})


def test_press_name_falls_back_to_the_domain_rather_than_inventing_one():
    assert c.press_of('https://www.yna.co.kr/view/1') == '연합뉴스'
    assert c.press_of('https://biz.sbs.co.kr/article/1') == 'biz.sbs.co.kr'


def test_clean_strips_the_search_highlight_markup():
    assert c.clean('&quot;<b>고용보험</b>&quot; 증가') == '"고용보험" 증가'


def test_search_keeps_only_the_window_and_stops_when_it_passes_it():
    pages = [
        {'total': 500, 'items': [item('고용보험 가입자 증가', pub='Mon, 07 Sep 2026 12:00:00 +0900')]},
        {'total': 500, 'items': [item('오래된 기사', pub='Fri, 01 Aug 2026 09:00:00 +0900')]},
        {'total': 500, 'items': [item('더 오래된', pub='Tue, 01 Jul 2026 09:00:00 +0900')]},
    ]
    calls = []

    def fake(url, hdr, timeout=10):
        calls.append(url)
        return pages[len(calls) - 1]

    a, b, _ = c.window_of('2026-09-07', False)
    kept, total, fetched, cut = c.search('q', a, b, 'id', 'sec', 'HUB', fetch=fake)
    assert [x['title'] for x in kept] == ['고용보험 가입자 증가']
    assert total == 500 and fetched == 2 and cut is False
    assert len(calls) == 2          # 구간을 지나면 더 안 넘긴다


def test_search_flags_truncation_instead_of_returning_quietly_short():
    # 1,000건을 다 넘겨도 구간에 못 닿으면 '보도가 적었다'가 아니라 '못 훑었다'다.
    page = {'total': 90000, 'items': [item('최신', pub='Mon, 07 Sep 2026 12:00:00 +0900')]}
    a, b, _ = c.window_of('2026-01-05', False)      # 한참 과거 회차
    kept, _, _, cut = c.search('q', a, b, 'id', 'sec', 'HUB',
                               fetch=lambda *_a, **_k: page)
    assert cut is True and kept == []


def test_search_stops_on_a_failed_page_without_losing_what_it_had():
    ok = {'total': 10, 'items': [item('고용보험 가입자 증가')]}
    state = {'n': 0}

    def flaky(url, hdr, timeout=10):
        state['n'] += 1
        if state['n'] == 1:
            return ok
        raise OSError('네트워크 끊김')

    a, b, _ = c.window_of('2026-09-07', False)
    kept, _, _, cut = c.search('q', a, b, 'id', 'sec', 'HUB', fetch=flaky, log=lambda _m: None)
    assert len(kept) == 1 and cut is False


def test_missing_credentials_are_an_error_not_a_silent_empty_round(monkeypatch):
    monkeypatch.delenv('NAVER_ID', raising=False)
    monkeypatch.delenv('NAVER_SECRET', raising=False)
    with pytest.raises(RuntimeError, match='NAVER_ID'):
        c.credentials()
    monkeypatch.setenv('NAVER_ID', '  ')
    monkeypatch.setenv('NAVER_SECRET', 'x')
    with pytest.raises(RuntimeError):
        c.credentials()


def test_mode_is_taken_from_the_env_when_pinned(monkeypatch):
    monkeypatch.setenv('NAVER_API_MODE', 'legacy')
    called = []
    assert c.detect_mode('id', 'sec', fetch=lambda *a, **k: called.append(1)) == 'LEGACY'
    assert not called                     # 못 박아 뒀으면 찔러 보지 않는다


def test_mode_detection_falls_through_to_legacy(monkeypatch):
    monkeypatch.delenv('NAVER_API_MODE', raising=False)

    def only_legacy(url, hdr, timeout=10):
        if 'naverapihub' in url:
            raise OSError('401')
        return {'total': 1}

    assert c.detect_mode('id', 'sec', fetch=only_legacy) == 'LEGACY'


def test_run_writes_the_round_file_and_keeps_what_it_dropped(tmp_path, monkeypatch):
    monkeypatch.setenv('NAVER_ID', 'id')
    monkeypatch.setenv('NAVER_SECRET', 'sec')
    monkeypatch.setenv('NAVER_API_MODE', 'HUB')
    page = {'total': 3, 'items': [
        item('고용보험 가입자 27만8천명 증가'),
        item('교보생명 체육대회 개막', desc='기업 소식'),
    ]}
    seen = {'n': 0}

    def fake(url, hdr, timeout=10):
        seen['n'] += 1
        return page if seen['n'] % 2 == 1 else {'total': 3, 'items': []}

    out = c.run('2026-09-07', hwpx=None, follow=False,
                fetch=fake, log=lambda _m: None, out_dir=str(tmp_path))
    assert out['volume']['articles'] == 1
    # 걸러진 기사도 파일에 남긴다 — 그날 무엇이 같이 돌았는지가 맥락이고,
    # 그물을 넓혀야 할지 나중에 다시 재려면 이게 있어야 한다.
    assert [x['title'] for x in out['excluded']] == ['교보생명 체육대회 개막']
    written = json.loads((tmp_path / 'articles_2026-09-07_regular.json').read_text('utf-8'))
    assert written['window'] == ['2026-09-07', '2026-09-08']


def test_hwpx_path_points_at_the_month_before_the_release():
    assert c.hwpx_for('2026-09-07').endswith('ei_2026-08.hwpx')
    assert c.hwpx_for('2026-01-05').endswith('ei_2025-12.hwpx')


def test_fetch_release_picks_the_hwpx_attachment():
    entry = {'attachments': [{'type': 'pdf', 'url': 'p'}, {'type': 'hwpx', 'url': 'h'}]}
    assert fr.hwpx_url(entry) == 'h'
    assert fr.hwpx_url({'attachments': []}) is None


def test_fetch_release_saves_and_skips_when_present(tmp_path):
    idx = {'2026-08': {'title': '2026년 8월 …동향',
                       'attachments': [{'type': 'hwpx', 'url': 'h'}]}}
    calls = []
    p = fr.save('2026-08', idx=idx, get=lambda u: calls.append(u) or b'PK\x03\x04',
                out_dir=str(tmp_path), log=lambda _m: None)
    assert calls == ['h'] and open(p, 'rb').read() == b'PK\x03\x04'
    fr.save('2026-08', idx=idx, get=lambda u: calls.append(u) or b'x',
            out_dir=str(tmp_path), log=lambda _m: None)
    assert calls == ['h']                 # 두 번째는 안 받는다


def test_a_round_not_on_the_board_yet_is_an_error(tmp_path):
    with pytest.raises(RuntimeError, match='없다'):
        fr.save('2099-01', idx={}, out_dir=str(tmp_path), log=lambda _m: None)
