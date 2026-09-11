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
