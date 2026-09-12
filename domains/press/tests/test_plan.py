import json

from domains.press.pipeline import plan
from domains.press.pipeline import run_round

RELEASES = ['2026-07-13', '2026-08-10', '2026-09-07', '2026-10-14']


def test_nothing_to_do_on_an_ordinary_day():
    # 후속 구간(D+1~D+21)과 그 마감일(D+22)을 지난 날.
    assert plan.decide('2026-10-05', RELEASES) == (None, None)


def test_release_day_and_the_next_collect_the_regular_round():
    # 수집 구간이 D~D+1 이라 이튿날 한 번 더 돌아야 그날 밤 기사가 담긴다.
    assert plan.decide('2026-09-07', RELEASES) == ('regular', '2026-09-07')
    assert plan.decide('2026-09-08', RELEASES) == ('regular', '2026-09-07')
    assert plan.decide('2026-09-09', RELEASES) == ('follow', '2026-09-07')


def test_follow_runs_every_day_while_its_window_is_open():
    # 한 번만 긁으면 후속 화면이 3주 내내 비어 있다가 갑자기 찬다. 그 사이에
    # 프레임이 번져도 아무도 모른다 — 이 도메인에서 가장 나쁜 것이 늦게 아는 것이다.
    for day in ('2026-09-09', '2026-09-15', '2026-09-28'):     # D+2 · D+8 · D+21
        assert plan.decide(day, RELEASES) == ('follow', '2026-09-07'), day


def test_follow_runs_once_more_the_day_its_window_closes():
    # 후속 구간은 D+1~D+21 이다. D+22 가 구간 전체를 담는 마지막 실행이다.
    assert plan.decide('2026-09-29', RELEASES) == ('follow', '2026-09-07')
    assert plan.decide('2026-09-30', RELEASES) == (None, None)


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
        json.dumps([{'n': 1, 'cites': True, 'why': 'x', 'tone': '긍정', 'focus': '주제',
                     'title': '이미 판정한 기사'}], ensure_ascii=False), encoding='utf-8')
    monkeypatch.setattr(run_round, 'RAW', str(tmp_path / 'raw'))
    monkeypatch.setattr(run_round, 'VERDICTS', str(tmp_path / 'verdicts'))
    monkeypatch.setattr(run_round, 'SOURCES', str(tmp_path))
    monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-x')

    asked = {}

    def fake(prompt):
        asked['prompt'] = prompt
        return json.dumps([{'n': 1, 'cites': False, 'why': '딴 얘기',
                            'tone': '중립', 'focus': ''}])

    n = run_round.judge_missing('2026-09-07', 'regular', call=fake, log=lambda _m: None)
    assert n == 1
    assert '새로 들어온 기사' in asked['prompt']
    assert '이미 판정한 기사' not in asked['prompt']

    merged = json.loads(
        (tmp_path / 'verdicts' / 'verdict_2026-09-07_regular.json').read_text('utf-8'))
    assert {v['title'] for v in merged} == {'이미 판정한 기사', '새로 들어온 기사'}


def test_a_verdict_without_a_tone_or_focus_is_asked_again(tmp_path, monkeypatch):
    # 논조·무게는 나중에 붙인 항목이라 옛 판정 파일에는 없다. 빈 값을 기본값으로
    # 채우면 판정이 없는 상태와 진짜 값이 화면에서 똑같아 보인다.
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
        return json.dumps([{'n': 1, 'cites': True, 'why': 'x',
                            'tone': '부정', 'focus': '언급'}])

    assert run_round.judge_missing('2026-09-07', 'regular',
                                   call=fake, log=lambda _m: None) == 1
    merged = json.loads(
        (tmp_path / 'verdicts' / 'verdict_2026-09-07_regular.json').read_text('utf-8'))
    # 다시 물은 기사의 옛 판정이 남으면 같은 제목이 두 줄이 된다.
    assert len(merged) == 1
    assert merged[0]['tone'] == '부정' and merged[0]['focus'] == '언급'


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


def test_make_data_refuses_to_shrink_the_round_list(tmp_path, monkeypatch):
    # 2026-09-11 에 실제로 일어난 일: CI 체크아웃에는 보도자료 hwpx 가 없어서
    # make_data 가 옛 회차를 건너뛰었고, rounds.json 이 3회차 → 1회차로 줄어든 채
    # 배포까지 나갔다. 조용히 줄어드는 것이 가장 나쁘다.
    import pytest
    from domains.press.pipeline import make_data

    data = tmp_path / 'data'
    raw = tmp_path / 'raw'
    data.mkdir()
    raw.mkdir()
    (data / 'rounds.json').write_text(json.dumps(
        [{'release': '2026-09-07'}, {'release': '2026-08-10'}], ensure_ascii=False),
        encoding='utf-8')
    (raw / 'articles_2026-09-07_regular.json').write_text('{}', encoding='utf-8')
    monkeypatch.setattr(make_data, 'DATA', str(data))
    monkeypatch.setattr(make_data, 'RAW', str(raw))
    monkeypatch.setattr(make_data, 'RELEASES', str(tmp_path / 'releases'))

    with pytest.raises(SystemExit, match='줄었다'):
        make_data.main()

    # 멈췄으니 옛 목록이 그대로 남아 있어야 한다.
    kept = json.loads((data / 'rounds.json').read_text('utf-8'))
    assert [r['release'] for r in kept] == ['2026-09-07', '2026-08-10']


def test_a_failed_judgement_does_not_throw_away_the_collection(tmp_path, monkeypatch):
    # 수집에는 마감이 있고(네이버 검색은 약 50일이면 그 회차에 못 닿는다) 판정에는
    # 없다. 판정 예외가 위로 올라가면 워크플로의 커밋 단계가 안 돌고, 러너가
    # 사라지면서 그날 긁은 원자료가 통째로 없어진다.
    raw = {'articles': [{'title': '새 기사', 'press': 'A', 'desc': ''}]}
    (tmp_path / 'raw').mkdir()
    (tmp_path / 'raw' / 'articles_2026-09-07_follow.json').write_text(
        json.dumps(raw, ensure_ascii=False), encoding='utf-8')
    monkeypatch.setattr(run_round, 'RAW', str(tmp_path / 'raw'))
    monkeypatch.setattr(run_round, 'VERDICTS', str(tmp_path / 'verdicts'))
    monkeypatch.setattr(run_round, 'SOURCES', str(tmp_path))
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-oa-exhausted')

    def quota_exceeded(_prompt):
        raise ValueError('API 가 429 를 돌려줬다: insufficient_quota')

    done = []
    monkeypatch.setattr(run_round, 'collect',
                        type('C', (), {'run': staticmethod(lambda *a, **k: done.append('collect'))}))
    monkeypatch.setattr(run_round, 'fetch_all_releases', lambda: done.append('hwpx'))
    monkeypatch.setattr(run_round.plan, 'save_state', lambda *a: done.append('state'))
    monkeypatch.setattr(run_round.fetch_release, 'save', lambda *a: None)
    import domains.press.pipeline.make_data as md
    monkeypatch.setattr(md, 'main', lambda: done.append('make_data'))
    monkeypatch.setattr(run_round.llm_cite, '_call_api', quota_exceeded)

    rc = run_round.main(['--release', '2026-09-07', '--kind', 'follow'])

    assert rc == 0                      # 죽지 않는다
    assert 'make_data' in done          # 조립까지 간다 = 커밋 단계가 돈다
    assert 'state' in done
