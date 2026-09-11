import json

from domains.press.pipeline import plan
from domains.press.pipeline import run_round

RELEASES = ['2026-07-13', '2026-08-10', '2026-09-07', '2026-10-14']


def test_nothing_to_do_on_an_ordinary_day():
    # 후속 구간(D+1~D+15)과 그 마감일(D+16)을 지난 날.
    assert plan.decide('2026-09-30', RELEASES) == (None, None)


def test_release_day_and_the_next_collect_the_regular_round():
    # 수집 구간이 D~D+1 이라 이튿날 한 번 더 돌아야 그날 밤 기사가 담긴다.
    assert plan.decide('2026-09-07', RELEASES) == ('regular', '2026-09-07')
    assert plan.decide('2026-09-08', RELEASES) == ('regular', '2026-09-07')
    assert plan.decide('2026-09-09', RELEASES) == ('follow', '2026-09-07')


def test_follow_runs_every_day_while_its_window_is_open():
    # 한 번만 긁으면 후속 화면이 보름 내내 비어 있다가 갑자기 찬다. 그 사이에
    # 프레임이 번져도 아무도 모른다 — 이 도메인에서 가장 나쁜 것이 늦게 아는 것이다.
    for day in ('2026-09-09', '2026-09-15', '2026-09-22'):     # D+2 · D+8 · D+15
        assert plan.decide(day, RELEASES) == ('follow', '2026-09-07'), day


def test_follow_runs_once_more_the_day_its_window_closes():
    # 후속 구간은 D+1~D+15 다. D+16 이 구간 전체를 담는 마지막 실행이다.
    assert plan.decide('2026-09-23', RELEASES) == ('follow', '2026-09-07')
    assert plan.decide('2026-09-24', RELEASES) == (None, None)


def test_the_day_after_the_release_stays_regular():
    # D+1 은 후속 구간의 첫날이지만 긁을 것이 하루치뿐이고, 그날은 정기 수집이
    # 배포 당일 밤 기사를 담아야 한다. 후속은 D+2 부터.
    assert plan.decide('2026-09-08', RELEASES) == ('regular', '2026-09-07')


def test_a_new_release_takes_over_from_the_previous_one():
    # 10/14 는 9/7 회차의 D+37 이자 새 회차의 배포일이다. 새 회차가 이긴다.
    assert plan.decide('2026-10-14', RELEASES) == ('regular', '2026-10-14')


def test_before_the_first_release_there_is_nothing_to_do():
    assert plan.decide('2026-07-01', RELEASES) == (None, None)
    assert plan.latest_release(RELEASES, plan._d('2026-07-01')) is None


def test_only_the_release_day_runs_every_hour():
    assert plan.is_release_day('2026-09-07', RELEASES)
    assert not plan.is_release_day('2026-09-08', RELEASES)
    assert not plan.is_release_day('2026-09-23', RELEASES)


def test_release_day_keeps_running_even_after_it_already_ran():
    done = {'release': '2026-09-07', 'kind': 'regular', 'date': '2026-09-07'}
    kind, release, why = plan.should_run('2026-09-07', RELEASES, done)
    assert (kind, release) == ('regular', '2026-09-07')
    assert '매시간' in why


def test_other_days_run_once_and_then_stop():
    kind, _, _ = plan.should_run('2026-09-08', RELEASES, None)
    assert kind == 'regular'
    done = {'release': '2026-09-07', 'kind': 'regular', 'date': '2026-09-08'}
    kind, _, why = plan.should_run('2026-09-08', RELEASES, done)
    assert kind is None and '이미 수집' in why


def test_yesterdays_record_does_not_block_todays_run():
    # 상태가 날짜별이어야 한다. 회차만 보면 이튿날 실행이 영영 안 돈다.
    stale = {'release': '2026-09-07', 'kind': 'regular', 'date': '2026-09-07'}
    kind, _, _ = plan.should_run('2026-09-08', RELEASES, stale)
    assert kind == 'regular'


def test_state_survives_a_broken_file(tmp_path):
    p = tmp_path / 'last_run.json'
    p.write_text('{망가진', encoding='utf-8')
    assert plan.load_state(str(p)) == {}      # 상태 파일 때문에 수집을 멈추지 않는다
    assert plan.load_state(str(tmp_path / '없다.json')) == {}


def test_state_round_trips(tmp_path):
    p = str(tmp_path / 'sub' / 'last_run.json')
    plan.save_state(p, '2026-09-07', 'regular', '2026-09-08')
    assert plan.load_state(p) == {'release': '2026-09-07', 'kind': 'regular',
                                  'date': '2026-09-08'}


def test_month_is_the_one_before_the_release():
    assert plan.month_of('2026-09-07') == '2026-08'
    assert plan.month_of('2026-01-05') == '2025-12'


def test_judge_only_asks_about_articles_that_have_no_verdict(tmp_path, monkeypatch):
    # 배포 당일 매시간 도는데 매번 전체를 다시 물으면 비용이 스물네 배가 된다.
    raw = {'articles': [
        {'title': '이미 판정한 기사', 'press': 'A', 'desc': ''},
        {'title': '새로 들어온 기사', 'press': 'B', 'desc': ''},
    ]}
    (tmp_path / 'raw').mkdir()
    (tmp_path / 'verdicts').mkdir()
    (tmp_path / 'raw' / 'articles_2026-09-07_regular.json').write_text(
        json.dumps(raw, ensure_ascii=False), encoding='utf-8')
    (tmp_path / 'verdicts' / 'verdict_2026-09-07_regular.json').write_text(
        json.dumps([{'n': 1, 'cites': True, 'why': 'x', 'tone': '긍정',
                     'title': '이미 판정한 기사'}], ensure_ascii=False), encoding='utf-8')
    monkeypatch.setattr(run_round, 'RAW', str(tmp_path / 'raw'))
    monkeypatch.setattr(run_round, 'VERDICTS', str(tmp_path / 'verdicts'))
    monkeypatch.setattr(run_round, 'SOURCES', str(tmp_path))
    monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-x')

    asked = {}

    def fake(prompt):
        asked['prompt'] = prompt
        return json.dumps([{'n': 1, 'cites': False, 'why': '딴 얘기', 'tone': '중립'}])

    n = run_round.judge_missing('2026-09-07', 'regular', call=fake, log=lambda _m: None)
    assert n == 1
    assert '새로 들어온 기사' in asked['prompt']
    assert '이미 판정한 기사' not in asked['prompt']

    merged = json.loads(
        (tmp_path / 'verdicts' / 'verdict_2026-09-07_regular.json').read_text('utf-8'))
    assert {v['title'] for v in merged} == {'이미 판정한 기사', '새로 들어온 기사'}


def test_a_verdict_without_a_tone_is_asked_again(tmp_path, monkeypatch):
    # 논조는 나중에 붙인 항목이라 옛 판정 파일에는 없다. 빈 값을 '중립'으로
    # 채우면 LLM 키가 없는 상태와 정말 중립인 회차가 화면에서 똑같아 보인다.
    raw = {'articles': [{'title': '논조 없는 옛 판정', 'press': 'A', 'desc': ''}]}
    (tmp_path / 'raw').mkdir()
    (tmp_path / 'verdicts').mkdir()
    (tmp_path / 'raw' / 'articles_2026-09-07_regular.json').write_text(
        json.dumps(raw, ensure_ascii=False), encoding='utf-8')
    (tmp_path / 'verdicts' / 'verdict_2026-09-07_regular.json').write_text(
        json.dumps([{'n': 1, 'cites': True, 'why': 'x', 'title': '논조 없는 옛 판정'}],
                   ensure_ascii=False), encoding='utf-8')
    monkeypatch.setattr(run_round, 'RAW', str(tmp_path / 'raw'))
    monkeypatch.setattr(run_round, 'VERDICTS', str(tmp_path / 'verdicts'))
    monkeypatch.setattr(run_round, 'SOURCES', str(tmp_path))
    monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-x')

    def fake(_prompt):
        return json.dumps([{'n': 1, 'cites': True, 'why': 'x', 'tone': '부정'}])

    assert run_round.judge_missing('2026-09-07', 'regular',
                                   call=fake, log=lambda _m: None) == 1
    merged = json.loads(
        (tmp_path / 'verdicts' / 'verdict_2026-09-07_regular.json').read_text('utf-8'))
    # 다시 물은 기사의 옛 판정이 남으면 같은 제목이 두 줄이 된다.
    assert len(merged) == 1 and merged[0]['tone'] == '부정'


def test_judging_is_skipped_without_a_key(tmp_path, monkeypatch):
    raw = {'articles': [{'title': 't', 'press': 'A', 'desc': ''}]}
    (tmp_path / 'raw').mkdir()
    (tmp_path / 'raw' / 'articles_2026-09-07_regular.json').write_text(
        json.dumps(raw, ensure_ascii=False), encoding='utf-8')
    monkeypatch.setattr(run_round, 'RAW', str(tmp_path / 'raw'))
    monkeypatch.setattr(run_round, 'VERDICTS', str(tmp_path / 'verdicts'))
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    msgs = []
    assert run_round.judge_missing('2026-09-07', 'regular', log=msgs.append) == 0
    assert any('키가 없다' in m for m in msgs)


SCHEDULE = {'1월': '2.9 (월)', '8월': '9.7 (월)', '9월': '10.14 (수)',
            '12월': '‘27년 미정'}


def test_schedule_table_becomes_absolute_release_dates():
    # 표는 「기준월 → 배포 월.일」이고 연도가 없다. 기준연도가 곧 배포연도다.
    got = plan.schedule_to_releases(SCHEDULE, 2026)
    assert got['2026-08'] == '2026-09-07'
    assert got['2026-09'] == '2026-10-14'
    assert got['2026-01'] == '2026-02-09'


def test_the_undecided_december_row_is_skipped_not_guessed():
    got = plan.schedule_to_releases(SCHEDULE, 2026)
    assert '2026-12' not in got


def test_a_nonsense_date_is_dropped_rather_than_crashing():
    assert plan.schedule_to_releases({'2월': '2.31 (월)'}, 2026) == {}
    assert plan.schedule_to_releases(None, 2026) == {}


def test_the_schedule_lets_the_gate_see_next_months_release():
    # 게시판을 안 두드려도 10/14 를 미리 안다 — 매시간 도는 게이트의 핵심이다.
    releases = sorted(plan.schedule_to_releases(SCHEDULE, 2026).values())
    assert plan.decide('2026-10-14', releases) == ('regular', '2026-10-14')
