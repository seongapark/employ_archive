import json

import pytest

from domains.press.pipeline import llm_cite as c

ARTS = [
    {'press': '뉴스1', 'title': '고용보험 가입자 27만8천명 증가', 'desc': '8개월 연속 증가세'},
    {'press': '한겨레', 'title': '육아휴직 급여 상한 인상안 심의', 'desc': '국회 환노위'},
]


def test_prompt_numbers_articles_so_the_answer_can_be_matched_back():
    p = c.build_prompt('2026년 8월 …동향', '2026-09-07', '요지', ARTS)
    assert '1. [뉴스1] 고용보험 가입자 27만8천명 증가' in p
    assert '2. [한겨레] 육아휴직 급여 상한 인상안 심의' in p


def test_prompt_carries_the_release_digest_not_just_its_title():
    # 요지가 빠지면 모델은 '고용 기사인가'만 보게 되고 회차를 못 가른다.
    p = c.build_prompt('제목', '2026-09-07', '가입자 1590만5천명, 전년비 27만8천명 증가', ARTS)
    assert '1590만5천명' in p


def test_prompt_asks_for_the_tone_of_the_headline_not_of_the_number():
    # 「구직급여 급증」과 「가입자 급증」은 같은 낱말인데 논조가 반대다.
    # 고정 어휘표가 원리적으로 못 하는 판단이라 프롬프트가 짚어 줘야 한다.
    p = c.build_prompt('제목', '2026-09-07', '요지', ARTS)
    assert '구직급여 신청 급증' in p and '가입자 급증' in p
    for t in c.TONES:
        assert t in p


def test_parses_verdicts_in_order():
    got = c.parse_response('[{"n":2,"cites":false,"why":"국회 심의","tone":"중립","focus":""},'
                           ' {"n":1,"cites":true,"why":"27만8천명","tone":"긍정","focus":"주제"}]', 2)
    assert [v.n for v in got] == [1, 2]
    assert got[0].cites is True and got[1].cites is False
    assert [v.tone for v in got] == ['긍정', '중립']


def test_accepts_a_fenced_answer():
    got = c.parse_response('```json\n[{"n":1,"cites":true,"tone":"부정","focus":"주제"}]\n```', 1)
    assert got[0].cites is True


def test_missing_article_is_an_error_not_a_silent_no():
    # 빠진 기사를 '인용 아님'으로 흘려보내면 누락이 화면에서 정상처럼 보인다.
    with pytest.raises(ValueError, match='빠진'):
        c.parse_response('[{"n":1,"cites":true,"tone":"긍정","focus":"주제"}]', 2)


def test_out_of_range_index_is_rejected():
    with pytest.raises(ValueError, match='범위'):
        c.parse_response('[{"n":1,"cites":true,"tone":"긍정","focus":"주제"},'
                         ' {"n":9,"cites":true,"tone":"긍정","focus":"주제"}]', 2)


def test_duplicate_index_is_rejected():
    with pytest.raises(ValueError, match='중복'):
        c.parse_response('[{"n":1,"cites":true,"tone":"긍정","focus":"주제"},'
                         ' {"n":1,"cites":false,"tone":"부정","focus":""}]', 2)


def test_missing_cites_field_is_rejected():
    # cites 가 없을 때 bool(None) 로 떨어지면 '인용 아님' 이 조용히 만들어진다.
    with pytest.raises(ValueError, match='cites'):
        c.parse_response('[{"n":1,"why":"…","tone":"긍정","focus":"주제"}]', 1)


def test_missing_tone_field_is_rejected():
    # 빈 논조를 '중립'으로 접으면 판정이 없는 상태와 정말 중립인 회차가
    # 화면에서 똑같아 보인다.
    with pytest.raises(ValueError, match='tone'):
        c.parse_response('[{"n":1,"cites":true,"why":"x","focus":"주제"}]', 1)


def test_an_unknown_tone_value_is_rejected():
    with pytest.raises(ValueError, match='tone'):
        c.parse_response('[{"n":1,"cites":true,"tone":"약간 긍정","focus":"주제"}]', 1)


def test_non_json_is_an_error():
    with pytest.raises(ValueError, match='JSON'):
        c.parse_response('판정할 수 없습니다', 1)


def test_judge_batches_and_renumbers_to_the_whole_list():
    arts = [{'press': 'p', 'title': f't{i}', 'desc': ''} for i in range(1, 26)]
    seen = []

    def fake(prompt):
        n = prompt.count('\n   ')          # 배치에 실린 기사 수
        seen.append(n)
        return json.dumps([{'n': i, 'cites': True, 'tone': '중립', 'focus': '주제'}
                           for i in range(1, n + 1)])

    got = c.judge('제목', '2026-09-07', '요지', arts, call=fake, log=lambda _: None)
    assert seen == [c.BATCH, len(arts) - c.BATCH]
    assert [v.n for v in got] == list(range(1, 26))


def test_provider_prefers_anthropic_then_openrouter_then_openai_then_none(monkeypatch):
    # 순서가 곧 선호다. 인용 판정 품질은 claude-opus-5 로 실측했으므로 그게 먼저다.
    for k in ('ANTHROPIC_API_KEY', 'OPENROUTER_API_KEY', 'OPENAI_API_KEY'):
        monkeypatch.delenv(k, raising=False)
    assert c.provider() is None

    monkeypatch.setenv('OPENAI_API_KEY', 'sk-oa-x')
    url, model, headers = c.provider()
    assert 'api.openai.com' in url and headers['Authorization'] == 'Bearer sk-oa-x'
    assert model == c.MODEL_OPENAI

    monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-x')
    url, model, headers = c.provider()
    assert 'openrouter' in url and headers['Authorization'] == 'Bearer sk-or-x'

    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-x')
    url, model, headers = c.provider()
    assert 'anthropic.com' in url and headers['x-api-key'] == 'sk-ant-x'


def test_openai_model_can_be_overridden(monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-oa-x')
    monkeypatch.setenv('OPENAI_MODEL', 'gpt-5.5-pro')
    assert c.provider()[1] == 'gpt-5.5-pro'


def test_openai_gets_max_completion_tokens_not_max_tokens():
    # gpt-5 계열은 max_tokens 를 400 으로 거부한다. 이름만 다른 게 아니라
    # 추론 토큰까지 그 한도에서 쓰므로 한도도 따로 잡는다.
    body = c.payload_for(c.OPENAI_URL, 'gpt-5.5', 'p')
    assert 'max_tokens' not in body
    assert body['max_completion_tokens'] == c.MAX_TOKENS_OPENAI

    for url in (c.ANTHROPIC_URL, c.OPENROUTER_URL):
        body = c.payload_for(url, 'm', 'p')
        assert body['max_tokens'] == c.MAX_TOKENS
        assert 'max_completion_tokens' not in body


def test_blank_key_is_treated_as_absent(monkeypatch):
    # 워크플로가 시크릿을 안 넣으면 빈 문자열이 들어온다 — 있는 것처럼 굴면
    # 401 을 받고 회차 전체가 판정 없이 끝난다.
    monkeypatch.setenv('ANTHROPIC_API_KEY', '   ')
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    assert c.provider() is None


def test_missing_focus_field_is_rejected():
    # 「수치를 전했나」와 「그 수치가 기사의 본론인가」는 다른 질문이다.
    # 빠진 것을 '주제'로 채우면 곁들인 인용이 후속 보도로 세어진다.
    with pytest.raises(ValueError, match='focus'):
        c.parse_response('[{"n":1,"cites":true,"tone":"긍정"}]', 1)


def test_an_unknown_focus_value_is_rejected():
    with pytest.raises(ValueError, match='focus'):
        c.parse_response('[{"n":1,"cites":true,"tone":"긍정","focus":"살짝"}]', 1)


def test_focus_is_blank_when_the_article_does_not_cite():
    # 인용이 아니면 무게를 따질 것이 없다. 모델이 뭘 보내든 비운다.
    got = c.parse_response('[{"n":1,"cites":false,"tone":"중립","focus":"주제"}]', 1)
    assert got[0].focus == ''


def test_prompt_tells_the_two_weights_apart():
    p = c.build_prompt('제목', '2026-09-07', '요지', ARTS)
    for f in c.FOCUSES:
        assert f in p
    assert '통계를 빼도 기사는 남는다' in p


# ── 구독(Claude Code CLI)으로 판정하기 ──────────────────────────────────────
# API 크레딧을 채우지 않고 Pro/Max 구독으로 돌리는 경로. HTTP 가 아니라
# `claude -p` 를 부르므로 provider() 의 url 자리에 센티넬이 들어가고 headers 는
# 빈 dict 다. reports·forecast 와 같은 스위치(JUDGE_PROVIDER)를 쓴다.

def test_the_cli_switch_wins_over_every_api_key(monkeypatch):
    # 구독으로 돌리려고 켠 스위치가 API 키에 밀리면, 잔액 0 인 키로 돌다가
    # 크레딧 부족으로 죽는다 — 구독으로 돌고 있다고 착각하기 가장 쉬운 실패다.
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-zero-balance')
    monkeypatch.setenv('JUDGE_PROVIDER', 'cli')
    url, model, headers = c.provider()
    assert url == c.CLI_URL
    assert model == c.MODEL_ANTHROPIC
    assert headers == {}


def test_without_the_switch_the_key_order_is_unchanged(monkeypatch):
    # 스위치를 켜지 않으면 기존 세 키 차례가 그대로여야 한다(회귀 방지).
    monkeypatch.delenv('JUDGE_PROVIDER', raising=False)
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-x')
    url, _, headers = c.provider()
    assert 'api.anthropic.com' in url and headers['x-api-key'] == 'sk-ant-x'


def test_the_cli_provider_is_not_none_so_the_round_does_not_skip_judging(monkeypatch):
    # run_round 는 provider() 가 None 이면 '키가 없다' 며 판정을 통째로 건너뛰고
    # 그 기사들을 화면에서 '인용 아님' 으로 센다. 구독 경로에서 None 이 나오면
    # 실패가 아니라 **조용한 오판정**이 된다.
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.setenv('JUDGE_PROVIDER', 'cli')
    assert c.provider() is not None


def _fake_cli(monkeypatch, *, result='[]', returncode=0, stderr=''):
    """subprocess.run 을 가로채고 argv·env·stdin 을 돌려준다."""
    seen = {}

    class Done:
        pass

    def fake_run(argv, **kw):
        seen['argv'] = argv
        seen['env'] = kw.get('env') or {}
        seen['input'] = kw.get('input')
        done = Done()
        done.returncode = returncode
        done.stdout = result if isinstance(result, str) else json.dumps(result)
        done.stderr = stderr
        return done

    monkeypatch.setattr(c.subprocess, 'run', fake_run)
    return seen


def test_the_prompt_goes_through_stdin_not_argv(monkeypatch):
    # 기사 20건에 요약까지 실으면 한 묶음이 수만 자다. argv 로 넘기면 리눅스는
    # 인자 하나가 128KiB 를 넘을 때, 윈도우는 명령줄이 32,767자를 넘을 때 죽는다 —
    # 둘 다 기사가 적은 회차에서는 멀쩡해 보인다.
    seen = _fake_cli(monkeypatch, result=json.dumps({'result': '[]'}))
    long_prompt = '가' * 40000
    c._call_cli(long_prompt)
    assert seen['input'] == long_prompt
    assert long_prompt not in seen['argv']


def test_the_cli_call_scrubs_api_keys_from_the_child_env(monkeypatch):
    # `claude -p` 의 인증 우선순위는 ANTHROPIC_API_KEY(3위) >
    # CLAUDE_CODE_OAUTH_TOKEN(5위) 이고, 비대화형(-p)에서는 키가 있으면 **항상**
    # 그걸 쓴다. 잔액 0 키가 환경에 남아 있으면 구독이 아니라 그 키로 돈다.
    seen = _fake_cli(monkeypatch, result=json.dumps({'result': '[]'}))
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-zero')
    monkeypatch.setenv('ANTHROPIC_AUTH_TOKEN', 'bearer-x')
    monkeypatch.setenv('CLAUDE_CODE_OAUTH_TOKEN', 'oat-live')

    c._call_cli('프롬프트')

    assert 'ANTHROPIC_API_KEY' not in seen['env']
    assert 'ANTHROPIC_AUTH_TOKEN' not in seen['env']
    assert seen['env']['CLAUDE_CODE_OAUTH_TOKEN'] == 'oat-live'


def test_the_cli_call_never_passes_bare(monkeypatch):
    # --bare 는 CLAUDE_CODE_OAUTH_TOKEN 을 안 읽는다 — 붙이면 인증이 통째로 안 된다.
    seen = _fake_cli(monkeypatch, result=json.dumps({'result': '[]'}))
    c._call_cli('프롬프트')
    assert '--bare' not in seen['argv']
    assert '-p' in seen['argv']


def test_the_cli_call_unwraps_the_json_envelope(monkeypatch):
    # --output-format json 은 답을 봉투에 담아 준다. 봉투째 넘기면 parse_response
    # 가 판정 배열이 아니라 봉투의 키들을 읽으려 한다.
    body = json.dumps([{'n': 1, 'cites': True, 'why': '수치 인용', 'tone': '긍정',
                        'focus': '주제'}], ensure_ascii=False)
    _fake_cli(monkeypatch, result=json.dumps({'type': 'result', 'is_error': False,
                                              'result': body}))
    assert c._call_cli('프롬프트') == body


def test_a_failing_cli_raises_instead_of_returning_nothing(monkeypatch):
    # 조용히 빈 문자열을 돌려주면 그 회차 기사가 전부 '인용 아님' 으로 지나간다.
    # 헤드리스 OAuth 토큰은 10~15분이면 만료된다 — 긴 배치에서 실제로 난다.
    _fake_cli(monkeypatch, result='', returncode=1,
              stderr='OAuth token has expired')
    with pytest.raises(ValueError) as got:
        c._call_cli('프롬프트')
    assert 'OAuth token has expired' in str(got.value)


def test_call_api_routes_the_cli_provider_to_the_cli(monkeypatch):
    # provider() 가 센티넬 url 을 돌려줬는데 _call_api 가 그걸 requests.post 에
    # 넘기면 cli:// 로 HTTP 를 치려 한다.
    monkeypatch.setenv('JUDGE_PROVIDER', 'cli')
    _fake_cli(monkeypatch, result=json.dumps({'result': 'ok'}))
    monkeypatch.setattr(c.requests, 'post',
                        lambda *a, **k: pytest.fail('CLI 경로가 HTTP 를 쳤다'))
    assert c._call_api('프롬프트') == 'ok'


def test_the_cli_model_can_be_swapped(monkeypatch):
    # Pro 요금제는 Opus 사용이 제한될 수 있다. provider() 와 _call_cli 가 같은
    # 값을 봐야 어느 모델이 판정했는지가 거짓이 되지 않는다.
    monkeypatch.setenv('JUDGE_PROVIDER', 'cli')
    monkeypatch.setenv('JUDGE_CLI_MODEL', 'claude-haiku-4-5-20251001')
    seen = _fake_cli(monkeypatch, result=json.dumps({'result': '[]'}))
    _, model, _ = c.provider()
    c._call_cli('프롬프트')
    assert model == 'claude-haiku-4-5-20251001'
    assert seen['argv'][seen['argv'].index('--model') + 1] == model
