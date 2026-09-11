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
    got = c.parse_response('[{"n":2,"cites":false,"why":"국회 심의","tone":"중립"},'
                           ' {"n":1,"cites":true,"why":"27만8천명","tone":"긍정"}]', 2)
    assert [v.n for v in got] == [1, 2]
    assert got[0].cites is True and got[1].cites is False
    assert [v.tone for v in got] == ['긍정', '중립']


def test_accepts_a_fenced_answer():
    got = c.parse_response('```json\n[{"n":1,"cites":true,"tone":"부정"}]\n```', 1)
    assert got[0].cites is True


def test_missing_article_is_an_error_not_a_silent_no():
    # 빠진 기사를 '인용 아님'으로 흘려보내면 누락이 화면에서 정상처럼 보인다.
    with pytest.raises(ValueError, match='빠진'):
        c.parse_response('[{"n":1,"cites":true,"tone":"긍정"}]', 2)


def test_out_of_range_index_is_rejected():
    with pytest.raises(ValueError, match='범위'):
        c.parse_response('[{"n":1,"cites":true,"tone":"긍정"},'
                         ' {"n":9,"cites":true,"tone":"긍정"}]', 2)


def test_duplicate_index_is_rejected():
    with pytest.raises(ValueError, match='중복'):
        c.parse_response('[{"n":1,"cites":true,"tone":"긍정"},'
                         ' {"n":1,"cites":false,"tone":"부정"}]', 2)


def test_missing_cites_field_is_rejected():
    # cites 가 없을 때 bool(None) 로 떨어지면 '인용 아님' 이 조용히 만들어진다.
    with pytest.raises(ValueError, match='cites'):
        c.parse_response('[{"n":1,"why":"…","tone":"긍정"}]', 1)


def test_missing_tone_field_is_rejected():
    # 빈 논조를 '중립'으로 접으면 판정이 없는 상태와 정말 중립인 회차가
    # 화면에서 똑같아 보인다.
    with pytest.raises(ValueError, match='tone'):
        c.parse_response('[{"n":1,"cites":true,"why":"x"}]', 1)


def test_an_unknown_tone_value_is_rejected():
    with pytest.raises(ValueError, match='tone'):
        c.parse_response('[{"n":1,"cites":true,"tone":"약간 긍정"}]', 1)


def test_non_json_is_an_error():
    with pytest.raises(ValueError, match='JSON'):
        c.parse_response('판정할 수 없습니다', 1)


def test_judge_batches_and_renumbers_to_the_whole_list():
    arts = [{'press': 'p', 'title': f't{i}', 'desc': ''} for i in range(1, 26)]
    seen = []

    def fake(prompt):
        n = prompt.count('\n   ')          # 배치에 실린 기사 수
        seen.append(n)
        return json.dumps([{'n': i, 'cites': True, 'tone': '중립'}
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
