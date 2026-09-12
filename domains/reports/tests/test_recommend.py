"""추천 판정. call 을 주입하므로 네트워크를 쓰지 않는다."""
import json
import re

import pytest

from domains.reports.pipeline import recommend
from domains.reports.pipeline.interests import Profile

PROFILE = Profile(text='## 청년 고용\n청년 일자리.\n## 임금·근로조건\n임금 격차.\n',
                  axes=['청년 고용', '임금·근로조건'], version='abcd1234')

ROWS = [
    {'id': 'bok-1', 'org': 'BOK', 'series': 'BOK 이슈노트',
     'title': '청년고용 위축, AI탓인가?', 'abstract': '경력 사다리 변화를 분석한다.'},
    {'id': 'kdi-2', 'org': 'KDI', 'series': '연구보고서',
     'title': '가계부채 리스크 평가', 'abstract': '가구 단위 신용위험.'},
]


def test_the_prompt_carries_the_profile_and_numbers_every_row():
    p = recommend.build_prompt(PROFILE, ROWS)
    assert '청년 고용' in p
    assert '1. ' in p and '2. ' in p
    assert '청년고용 위축' in p
    # id 를 모델에 주지 않는다 — 지어내면 엉뚱한 레코드에 붙는다.
    assert 'bok-1' not in p


def test_a_well_formed_response_is_read():
    body = json.dumps([
        {'n': 1, 'pick': True, 'axis': '청년 고용', 'why': '청년 경력 사다리를 분해'},
        {'n': 2, 'pick': False, 'axis': '', 'why': '가계부채 — 고용과 무관'},
    ], ensure_ascii=False)
    got = recommend.parse_response(body, 2, PROFILE.axes)
    assert got[0].pick is True and got[0].axis == '청년 고용'
    assert got[1].pick is False


def test_a_fenced_response_is_read():
    body = '```json\n[{"n":1,"pick":true,"axis":"청년 고용","why":"ㄱ"},' \
           '{"n":2,"pick":false,"axis":"","why":"ㄴ"}]\n```'
    assert len(recommend.parse_response(body, 2, PROFILE.axes)) == 2


def test_a_missing_row_is_an_error_not_a_silent_false():
    body = json.dumps([{'n': 1, 'pick': True, 'axis': '청년 고용', 'why': 'ㄱ'}])
    with pytest.raises(ValueError, match='빠진'):
        recommend.parse_response(body, 2, PROFILE.axes)


def test_an_unknown_axis_is_an_error():
    body = json.dumps([{'n': 1, 'pick': True, 'axis': '없는축', 'why': 'ㄱ'}],
                      ensure_ascii=False)
    with pytest.raises(ValueError, match='축'):
        recommend.parse_response(body, 1, PROFILE.axes)


def test_a_pick_without_a_reason_is_an_error():
    body = json.dumps([{'n': 1, 'pick': True, 'axis': '청년 고용', 'why': ''}],
                      ensure_ascii=False)
    with pytest.raises(ValueError, match='이유'):
        recommend.parse_response(body, 1, PROFILE.axes)


def test_axis_matching_ignores_whitespace_but_stores_the_canonical_name():
    # 모델이 '청년 고용' 을 '청년고용' 으로 쓰는 정도의 한 글자 차이로
    # 묶음 20건 전체를 잃으면 안 된다. 공백만 눌러 대조하고, 저장은
    # 프로파일의 정식 이름('청년 고용', 공백 있음)으로 한다.
    body = json.dumps([{'n': 1, 'pick': True, 'axis': '청년고용', 'why': 'ㄱ'}],
                      ensure_ascii=False)
    got = recommend.parse_response(body, 1, PROFILE.axes)
    assert got[0].axis == '청년 고용'


def test_a_non_picked_row_with_an_unknown_axis_is_not_an_error():
    # 안 고른 항목의 axis 는 버리는 값이라 검증하지 않는다(의도).
    body = json.dumps([{'n': 1, 'pick': False, 'axis': '없는축', 'why': 'ㄱ'}],
                      ensure_ascii=False)
    got = recommend.parse_response(body, 1, PROFILE.axes)
    assert got[0].pick is False and got[0].axis == ''


def test_a_string_pick_is_an_error_even_when_falsy():
    # bool("false") 는 파이썬에서 True 다 — 느슨하게 받으면 안 고른 보고서가
    # 추천으로 둔갑한다. 진짜 불리언만 받는다.
    body = json.dumps([{'n': 1, 'pick': 'false', 'axis': '청년 고용', 'why': 'ㄱ'}],
                      ensure_ascii=False)
    with pytest.raises(ValueError, match='불리언'):
        recommend.parse_response(body, 1, PROFILE.axes)


def test_a_string_true_pick_is_also_an_error():
    body = json.dumps([{'n': 1, 'pick': 'true', 'axis': '청년 고용', 'why': 'ㄱ'}],
                      ensure_ascii=False)
    with pytest.raises(ValueError, match='불리언'):
        recommend.parse_response(body, 1, PROFILE.axes)


def test_a_numeric_pick_is_an_error():
    body = json.dumps([{'n': 1, 'pick': 0, 'axis': '청년 고용', 'why': 'ㄱ'}],
                      ensure_ascii=False)
    with pytest.raises(ValueError, match='불리언'):
        recommend.parse_response(body, 1, PROFILE.axes)

    body = json.dumps([{'n': 1, 'pick': 1, 'axis': '청년 고용', 'why': 'ㄱ'}],
                      ensure_ascii=False)
    with pytest.raises(ValueError, match='불리언'):
        recommend.parse_response(body, 1, PROFILE.axes)


def test_a_non_array_response_is_an_error():
    body = json.dumps({'n': 1, 'pick': True, 'axis': '청년 고용', 'why': 'ㄱ'},
                      ensure_ascii=False)
    with pytest.raises(ValueError, match='배열'):
        recommend.parse_response(body, 1, PROFILE.axes)


def test_a_non_object_row_is_an_error():
    body = json.dumps(['이건 객체가 아니다'], ensure_ascii=False)
    with pytest.raises(ValueError, match='객체'):
        recommend.parse_response(body, 1, PROFILE.axes)


def test_an_out_of_range_n_is_an_error():
    body = json.dumps([{'n': 5, 'pick': True, 'axis': '청년 고용', 'why': 'ㄱ'}],
                      ensure_ascii=False)
    with pytest.raises(ValueError, match='범위'):
        recommend.parse_response(body, 1, PROFILE.axes)


def test_a_duplicate_n_is_an_error():
    body = json.dumps([
        {'n': 1, 'pick': True, 'axis': '청년 고용', 'why': 'ㄱ'},
        {'n': 1, 'pick': False, 'axis': '', 'why': 'ㄴ'},
    ], ensure_ascii=False)
    with pytest.raises(ValueError, match='중복'):
        recommend.parse_response(body, 2, PROFILE.axes)


def test_axis_matching_also_ignores_the_middle_dot():
    # 모델이 '임금·근로조건' 의 가운뎃점을 공백으로 바꿔 쓰는 정도의 차이로
    # 묶음 20건 전체가 죽으면 안 된다. 공백뿐 아니라 '·' 도 눌러 대조하고,
    # 저장은 프로파일의 정식 이름('임금·근로조건', 가운뎃점 있음)으로 한다.
    body = json.dumps([{'n': 1, 'pick': True, 'axis': '임금 근로조건', 'why': 'ㄱ'}],
                      ensure_ascii=False)
    got = recommend.parse_response(body, 1, PROFILE.axes)
    assert got[0].axis == '임금·근로조건'


def test_judge_splits_into_batches_and_renumbers_globally():
    # 25건이면 20 + 5 두 묶음이다. 묶음마다 n 은 1부터 다시 세지만,
    # 돌려줄 때는 전체 기준 번호여야 호출자가 id 에 되맞출 수 있다.
    sizes = []

    def fake_call(prompt):
        n = sum(1 for line in prompt.splitlines()
                if re.match(r'^\d+\. \[', line))
        sizes.append(n)
        return json.dumps([{'n': i + 1, 'pick': False, 'axis': '', 'why': 'ㄱ'}
                           for i in range(n)], ensure_ascii=False)

    rows = [dict(ROWS[0], id=f'r-{i}') for i in range(25)]
    got = recommend.judge(PROFILE, rows, call=fake_call, log=lambda *_: None)
    assert sizes == [20, 5]
    assert [v.n for v in got] == list(range(1, 26))


def test_an_already_judged_report_is_not_asked_again():
    cache = {'bok-1': {'pick': True, 'axis': '청년 고용', 'why': 'ㄱ',
                       'basis': 'abstract', 'model': 'claude-opus-5',
                       'profile_version': 'abcd1234', 'judged_at': 'x'}}
    todo = recommend.pending(ROWS, cache, PROFILE)
    assert [r['id'] for r in todo] == ['kdi-2']


def test_a_changed_profile_forces_a_rejudge():
    cache = {'bok-1': {'pick': True, 'axis': '청년 고용', 'why': 'ㄱ',
                       'basis': 'abstract', 'model': 'claude-opus-5',
                       'profile_version': '옛버전', 'judged_at': 'x'}}
    todo = recommend.pending(ROWS, cache, PROFILE)
    assert sorted(r['id'] for r in todo) == ['bok-1', 'kdi-2']


def test_the_basis_records_whether_an_abstract_was_available():
    rows = [dict(ROWS[0]), dict(ROWS[1], abstract='')]
    verdicts = [recommend.Verdict(1, True, '청년 고용', 'ㄱ'),
                recommend.Verdict(2, False, '', 'ㄴ')]
    cache = recommend.merge({}, rows, verdicts, PROFILE)
    assert cache['bok-1']['basis'] == 'abstract'
    assert cache['kdi-2']['basis'] == 'title'


def test_merge_keeps_earlier_entries_for_reports_not_rejudged():
    old = {'old-1': {'pick': False, 'axis': '', 'why': 'ㄱ', 'basis': 'title',
                     'model': 'claude-opus-5', 'profile_version': 'abcd1234',
                     'judged_at': 'x'}}
    cache = recommend.merge(old, [ROWS[0]], [recommend.Verdict(1, True, '청년 고용', 'ㄴ')],
                            PROFILE)
    assert 'old-1' in cache and 'bok-1' in cache


def test_a_mid_run_failure_keeps_the_earlier_batches_on_disk(tmp_path):
    # 45건 = 20 + 20 + 5, 세 묶음. 세 번째 묶음에서 예외가 나도 앞의 두
    # 묶음(40건)은 파일에 남아 있어야 한다 — 이게 이 과제의 핵심 요건이다.
    # 다시 돌리면 pending() 이 이미 판정한 40건을 걸러 5건만 다시 묻는다.
    cache_path = tmp_path / 'recommendations.json'
    rows = [dict(ROWS[0], id=f'r-{i}', title=f'제목 {i}') for i in range(45)]
    calls = []

    def fake_call(prompt):
        calls.append(prompt)
        if len(calls) == 3:
            raise RuntimeError('모의 API 오류')
        n = sum(1 for line in prompt.splitlines() if re.match(r'^\d+\. \[', line))
        return json.dumps([{'n': i + 1, 'pick': False, 'axis': '', 'why': 'ㄱ'}
                           for i in range(n)], ensure_ascii=False)

    with pytest.raises(RuntimeError, match='모의 API 오류'):
        recommend.judge_and_cache(PROFILE, rows, {}, call=fake_call,
                                  cache_path=cache_path, log=lambda *_: None)

    assert len(calls) == 3
    on_disk = json.loads(cache_path.read_text(encoding='utf-8'))
    assert len(on_disk) == 40
    assert all(f'r-{i}' in on_disk for i in range(40))
    assert not any(f'r-{i}' in on_disk for i in range(40, 45))

    # 재실행 시늉: 이미 판정한 40건은 다시 안 묻는다.
    still_todo = recommend.pending(rows, on_disk, PROFILE)
    assert sorted(r['id'] for r in still_todo) == sorted(f'r-{i}' for i in range(40, 45))


def test_provider_prefers_anthropic_then_openrouter_then_openai_then_none(monkeypatch):
    # 순서가 곧 선호다 — 판정 품질은 claude-opus-5 로 프롬프트를 설계했다.
    for k in ('ANTHROPIC_API_KEY', 'OPENROUTER_API_KEY', 'OPENAI_API_KEY'):
        monkeypatch.delenv(k, raising=False)
    assert recommend.provider() is None

    monkeypatch.setenv('OPENAI_API_KEY', 'sk-oa-x')
    url, model, headers = recommend.provider()
    assert 'api.openai.com' in url and headers['Authorization'] == 'Bearer sk-oa-x'
    assert model == recommend.MODEL_OPENAI

    monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-x')
    url, model, headers = recommend.provider()
    assert 'openrouter' in url and headers['Authorization'] == 'Bearer sk-or-x'

    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-x')
    url, model, headers = recommend.provider()
    assert 'anthropic.com' in url and headers['x-api-key'] == 'sk-ant-x'


def test_openai_model_can_be_overridden(monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-oa-x')
    monkeypatch.setenv('OPENAI_MODEL', 'gpt-5.5-pro')
    assert recommend.provider()[1] == 'gpt-5.5-pro'


def test_openai_gets_max_completion_tokens_not_max_tokens():
    # gpt-5 계열은 max_tokens 를 400 으로 거부한다. 이름만 다른 게 아니라
    # 추론 토큰까지 그 한도에서 쓰므로 한도도 따로 잡는다.
    body = recommend.payload_for(recommend.OPENAI_URL, 'gpt-5.5', 'p')
    assert 'max_tokens' not in body
    assert body['max_completion_tokens'] == recommend.MAX_TOKENS_OPENAI

    for url in (recommend.ANTHROPIC_URL, recommend.OPENROUTER_URL):
        body = recommend.payload_for(url, 'm', 'p')
        assert body['max_tokens'] == recommend.MAX_TOKENS
        assert 'max_completion_tokens' not in body


def test_merge_records_the_model_that_actually_judged(monkeypatch):
    # 실측(2026-09-11): 이 저장소엔 OPENAI_API_KEY 밖에 없어 실제로는
    # gpt-5.5 로 판정했는데, merge() 가 MODEL_ANTHROPIC 상수를 그대로
    # 박는 바람에 캐시엔 전부 claude-opus-5 로 거짓 기록됐다. model 은
    # "누가 판정했나"의 유일한 기록이라, 상수를 박으면 나중에 앤트로픽
    # 키가 들어와도 무엇을 gpt-5.5 로 다시 물어야 할지 구분할 수 없다.
    for k in ('ANTHROPIC_API_KEY', 'OPENROUTER_API_KEY', 'OPENAI_API_KEY'):
        monkeypatch.delenv(k, raising=False)

    monkeypatch.setenv('OPENAI_API_KEY', 'sk-oa-x')
    _, model, _ = recommend.provider()
    cache = recommend.merge({}, [ROWS[0]], [recommend.Verdict(1, True, '청년 고용', 'ㄱ')],
                            PROFILE, model=model)
    assert cache['bok-1']['model'] == 'gpt-5.5'

    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-x')
    _, model, _ = recommend.provider()
    cache = recommend.merge({}, [ROWS[0]], [recommend.Verdict(1, True, '청년 고용', 'ㄱ')],
                            PROFILE, model=model)
    assert cache['bok-1']['model'] == 'claude-opus-5'


def test_main_records_a_failed_attempt_and_reraises(tmp_path, monkeypatch):
    # 판정 실패가 조용히 사라진 사고를 막는 테스트다: 워크플로가
    # continue-on-error 라 실패해도 전체 실행은 '성공'으로 남고, 예외가
    # main() 을 그대로 뚫고 올라가면 last_run.json 에는 시도한 흔적조차
    # 안 남는다(2,236건 중 356건이 미판정인 채 아무도 몰랐던 사고). try/finally
    # 로 감싸 실패해도 기록은 남기되, 예외는 그대로 다시 던져 워크플로가
    # 실패를 실패로 안다.
    monkeypatch.setattr(recommend, 'DATA', tmp_path)
    reports = [{'id': f'r-{i}', 'org': 'BOK', 'series': 'BOK 이슈노트',
               'title': f'제목 {i}'} for i in range(3)]
    (tmp_path / 'reports.json').write_text(json.dumps(reports, ensure_ascii=False),
                                           encoding='utf-8')
    (tmp_path / 'abstracts.json').write_text('{}', encoding='utf-8')

    def boom(prompt):
        raise RuntimeError('API 가 429 를 돌려줬다: insufficient_quota')

    with pytest.raises(RuntimeError, match='429'):
        recommend.main([], call=boom)

    last = json.loads((tmp_path / 'last_run.json').read_text(encoding='utf-8'))
    rec = last['recommend']
    assert rec['judged'] == 0
    assert rec['unjudged'] == 3
    assert rec['picked'] == 0
    assert '429' in rec['error']
    assert 'at' in rec and 'profile_version' in rec


def test_main_keeps_the_batches_judged_before_a_later_failure(tmp_path, monkeypatch):
    # 45건 = 20 + 20 + 5, 세 묶음. 세 번째에서 실패해도 앞선 40건은 디스크에
    # 남아 있고(judge_and_cache 의 기존 보장), main() 이 다시 읽어 그 40건을
    # judged 로, 나머지 5건을 unjudged 로 남겨야 한다.
    monkeypatch.setattr(recommend, 'DATA', tmp_path)
    reports = [{'id': f'r-{i}', 'org': 'BOK', 'series': 'BOK 이슈노트',
               'title': f'제목 {i}'} for i in range(45)]
    (tmp_path / 'reports.json').write_text(json.dumps(reports, ensure_ascii=False),
                                           encoding='utf-8')
    (tmp_path / 'abstracts.json').write_text('{}', encoding='utf-8')
    calls = []

    def flaky(prompt):
        calls.append(prompt)
        if len(calls) == 3:
            raise RuntimeError('모의 API 오류')
        n = sum(1 for line in prompt.splitlines() if re.match(r'^\d+\. \[', line))
        return json.dumps([{'n': i + 1, 'pick': False, 'axis': '', 'why': 'ㄱ'}
                           for i in range(n)], ensure_ascii=False)

    with pytest.raises(RuntimeError, match='모의 API 오류'):
        recommend.main([], call=flaky)

    last = json.loads((tmp_path / 'last_run.json').read_text(encoding='utf-8'))
    rec = last['recommend']
    assert rec['judged'] == 40
    assert rec['unjudged'] == 5
    assert '모의 API 오류' in rec['error']


def test_judge_and_cache_records_the_actual_provider_model(monkeypatch, tmp_path):
    # merge() 단위 테스트와 별도로, main() 이 실제로 부르는 경로인
    # judge_and_cache() 도 provider() 가 고른 모델을 그대로 캐시에
    # 남기는지 재확인한다.
    for k in ('ANTHROPIC_API_KEY', 'OPENROUTER_API_KEY'):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-oa-x')

    def fake_call(prompt):
        return json.dumps([{'n': 1, 'pick': True, 'axis': '청년 고용', 'why': 'ㄱ'}],
                          ensure_ascii=False)

    cache_path = tmp_path / 'recommendations.json'
    cache = recommend.judge_and_cache(PROFILE, [ROWS[0]], {}, call=fake_call,
                                      cache_path=cache_path, log=lambda *_: None)
    assert cache['bok-1']['model'] == 'gpt-5.5'
    on_disk = json.loads(cache_path.read_text(encoding='utf-8'))
    assert on_disk['bok-1']['model'] == 'gpt-5.5'


# ── 선택적 재판정: 뒤집힐 수 있는 것만 다시 묻는다 ──────────────────────
#
# 축을 늘리면 profile_version 이 바뀌어 캐시가 통째로 낡는다. 하지만 늘린
# 축은 추천을 늘릴 뿐 줄이지 않으므로, 기각됐던 것 중 새 키워드 주제에
# 닿는 것만 뒤집힐 수 있다. plan_rejudge() 가 그 갈래를 낸다.

TOPIC_KEYWORDS = {'고령자': ['고령자', '정년', '계속고용'], '외국인력': ['외국인력']}

REJ_ROWS = [
    {'id': 'r-hit', 'org': 'X', 'series': 'Y',
     'title': '고령자 계속고용 정책 평가', 'abstract': ''},
    {'id': 'r-miss', 'org': 'X', 'series': 'Y',
     'title': '가계부채 리스크 평가', 'abstract': ''},
    {'id': 'r-new', 'org': 'X', 'series': 'Y',
     'title': '신규 미판정 보고서', 'abstract': ''},
]


def _old(pick=False, axis='', why='ㄱ', profile_version='old-ver'):
    return {'pick': pick, 'axis': axis, 'why': why, 'basis': 'title',
            'model': 'claude-opus-5', 'profile_version': profile_version,
            'judged_at': 'x'}


def test_plan_rejudge_asks_only_keyword_hits_and_separates_the_unjudged():
    cache = {'r-hit': _old(pick=False), 'r-miss': _old(pick=False)}
    plan = recommend.plan_rejudge(REJ_ROWS, cache, PROFILE, ['고령자'],
                                  keywords=TOPIC_KEYWORDS)
    assert [r['id'] for r in plan.ask] == ['r-hit']
    assert [r['id'] for r in plan.carry] == ['r-miss']
    assert [r['id'] for r in plan.unjudged] == ['r-new']


def test_plan_rejudge_leaves_up_to_date_rows_alone():
    # 이미 최신 프로파일로 판정된 것은 다시 묻지도 이어받지도 않는다.
    cache = {'r-hit': _old(pick=False, profile_version=PROFILE.version)}
    plan = recommend.plan_rejudge([REJ_ROWS[0]], cache, PROFILE, ['고령자'],
                                  keywords=TOPIC_KEYWORDS)
    assert plan.ask == [] and plan.carry == [] and plan.unjudged == []


def test_plan_rejudge_always_reasks_a_recommended_row_whose_axis_vanished():
    # 축을 줄이거나 이름을 바꾼 경우: 이미 추천된 레코드의 axis 가 새
    # 프로파일에 없으면, 키워드에 안 걸려도 반드시 다시 묻는다 — 이어받으면
    # 화면에서 없는 축에 묶인다.
    cache = {'r-miss': _old(pick=True, axis='없어진축')}
    plan = recommend.plan_rejudge([REJ_ROWS[1]], cache, PROFILE, ['고령자'],
                                  keywords=TOPIC_KEYWORDS)
    assert [r['id'] for r in plan.ask] == ['r-miss']
    assert plan.carry == []


def test_plan_rejudge_does_not_reask_a_rejected_row_whose_axis_field_is_empty():
    # 기각된 레코드는 axis 가 애초에 빈 문자열이다 — '축이 사라졌다'는
    # 안전장치가 기각 레코드에는 적용되지 않고, 그냥 키워드로만 가른다.
    cache = {'r-miss': _old(pick=False, axis='')}
    plan = recommend.plan_rejudge([REJ_ROWS[1]], cache, PROFILE, ['고령자'],
                                  keywords=TOPIC_KEYWORDS)
    assert plan.ask == [] and [r['id'] for r in plan.carry] == ['r-miss']


def test_plan_rejudge_rejects_a_topic_not_in_keywords_json():
    with pytest.raises(ValueError, match='keywords.json'):
        recommend.plan_rejudge(REJ_ROWS, {}, PROFILE, ['없는주제'], keywords=TOPIC_KEYWORDS)


def test_carry_over_keeps_the_old_verdict_but_marks_where_it_came_from():
    cache = {'r-miss': _old(pick=True, axis='청년 고용', why='경력 사다리 분석',
                            profile_version='old-ver')}
    got = recommend.carry_over(cache, [REJ_ROWS[1]], PROFILE)
    row = got['r-miss']
    # pick·axis·why 는 옛 판정 그대로다 — LLM 을 다시 안 불렀으니 바뀔 이유가
    # 없다.
    assert row['pick'] is True
    assert row['axis'] == '청년 고용'
    assert row['why'] == '경력 사다리 분석'
    # profile_version 은 새 값으로 바뀐다 — 안 바꾸면 pending() 이 다음
    # 실행에서 또 낡았다고 보고 이어받기를 반복한다.
    assert row['profile_version'] == PROFILE.version
    # carried_from 에 원래 판정한 프로파일을 남긴다 — profile_version 만
    # 새 값이면 "새 프로파일이 판정했다"는 거짓이 된다.
    assert row['carried_from'] == 'old-ver'


def test_main_rejudge_keywords_calls_the_llm_only_for_matches(tmp_path, monkeypatch):
    # main() 은 실제 data/interests.md · data/keywords.json 을 읽는다(그
    # 경로는 recommend.DATA 로 갈아끼울 수 없다) — 실제 저장소의 '고령자'
    # 주제로 시험한다.
    monkeypatch.setattr(recommend, 'DATA', tmp_path)
    reports = [
        {'id': 'r-hit', 'org': 'X', 'series': 'Y', 'title': '고령자 계속고용 정책 평가'},
        {'id': 'r-miss', 'org': 'X', 'series': 'Y', 'title': '가계부채 리스크 평가'},
    ]
    (tmp_path / 'reports.json').write_text(json.dumps(reports, ensure_ascii=False),
                                           encoding='utf-8')
    (tmp_path / 'abstracts.json').write_text('{}', encoding='utf-8')
    old_cache = {'r-hit': _old(pick=False), 'r-miss': _old(pick=False)}
    (tmp_path / 'recommendations.json').write_text(
        json.dumps(old_cache, ensure_ascii=False), encoding='utf-8')

    calls = []

    def fake_call(prompt):
        calls.append(prompt)
        return json.dumps([{'n': 1, 'pick': False, 'axis': '', 'why': 'ㄱ'}],
                          ensure_ascii=False)

    recommend.main(['--rejudge-keywords', '고령자'], call=fake_call)

    assert len(calls) == 1  # r-hit 만 물었다
    on_disk = json.loads((tmp_path / 'recommendations.json').read_text(encoding='utf-8'))
    assert 'carried_from' not in on_disk['r-hit']       # 이번에 실제로 판정했다
    assert on_disk['r-miss']['carried_from'] == 'old-ver'  # 이어받았다


def test_dry_run_needs_no_api_key_and_prints_the_three_counts(tmp_path, monkeypatch, capsys):
    for k in ('ANTHROPIC_API_KEY', 'OPENROUTER_API_KEY', 'OPENAI_API_KEY'):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(recommend, 'DATA', tmp_path)
    reports = [
        {'id': 'r-hit', 'org': 'X', 'series': 'Y', 'title': '고령자 계속고용 정책 평가'},
        {'id': 'r-miss', 'org': 'X', 'series': 'Y', 'title': '가계부채 리스크 평가'},
        {'id': 'r-new', 'org': 'X', 'series': 'Y', 'title': '신규 미판정 보고서'},
    ]
    (tmp_path / 'reports.json').write_text(json.dumps(reports, ensure_ascii=False),
                                           encoding='utf-8')
    (tmp_path / 'abstracts.json').write_text('{}', encoding='utf-8')
    old_cache = {'r-hit': _old(pick=False), 'r-miss': _old(pick=False)}
    (tmp_path / 'recommendations.json').write_text(
        json.dumps(old_cache, ensure_ascii=False), encoding='utf-8')

    rc = recommend.main(['--dry-run', '--rejudge-keywords', '고령자'])

    assert rc == 0
    out = capsys.readouterr().out
    assert '다시 물을 것 1건' in out
    assert '이어받을 것 1건' in out
    assert '안 물어본 것 1건' in out
    # dry-run 은 이어받기조차 쓰지 않는다 — 캐시 파일이 그대로여야 한다.
    on_disk = json.loads((tmp_path / 'recommendations.json').read_text(encoding='utf-8'))
    assert on_disk == old_cache


def test_without_the_option_main_still_rejudges_everything(tmp_path, monkeypatch):
    # 옵션을 안 주면 종전대로 낡은 것 전부를 다시 묻는다 — 이어받기는
    # 전혀 관여하지 않는다.
    monkeypatch.setattr(recommend, 'DATA', tmp_path)
    reports = [
        {'id': 'r-hit', 'org': 'X', 'series': 'Y', 'title': '고령자 계속고용 정책 평가'},
        {'id': 'r-miss', 'org': 'X', 'series': 'Y', 'title': '가계부채 리스크 평가'},
    ]
    (tmp_path / 'reports.json').write_text(json.dumps(reports, ensure_ascii=False),
                                           encoding='utf-8')
    (tmp_path / 'abstracts.json').write_text('{}', encoding='utf-8')
    old_cache = {'r-hit': _old(pick=False), 'r-miss': _old(pick=False)}
    (tmp_path / 'recommendations.json').write_text(
        json.dumps(old_cache, ensure_ascii=False), encoding='utf-8')

    calls = []

    def fake_call(prompt):
        calls.append(prompt)
        n = sum(1 for line in prompt.splitlines() if re.match(r'^\d+\. \[', line))
        return json.dumps([{'n': i + 1, 'pick': False, 'axis': '', 'why': 'ㄱ'}
                           for i in range(n)], ensure_ascii=False)

    recommend.main([], call=fake_call)

    assert len(calls) == 1  # 두 건 다 한 묶음으로 같이 다시 물었다
    on_disk = json.loads((tmp_path / 'recommendations.json').read_text(encoding='utf-8'))
    assert 'carried_from' not in on_disk['r-hit']
    assert 'carried_from' not in on_disk['r-miss']
