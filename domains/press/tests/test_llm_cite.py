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


def test_parses_verdicts_in_order():
    got = c.parse_response('[{"n":2,"cites":false,"why":"국회 심의"},'
                           ' {"n":1,"cites":true,"why":"27만8천명"}]', 2)
    assert [v.n for v in got] == [1, 2]
    assert got[0].cites is True and got[1].cites is False


def test_accepts_a_fenced_answer():
    got = c.parse_response('```json\n[{"n":1,"cites":true}]\n```', 1)
    assert got[0].cites is True


def test_missing_article_is_an_error_not_a_silent_no():
    # 빠진 기사를 '인용 아님'으로 흘려보내면 누락이 화면에서 정상처럼 보인다.
    with pytest.raises(ValueError, match='빠진'):
        c.parse_response('[{"n":1,"cites":true}]', 2)


def test_out_of_range_index_is_rejected():
    with pytest.raises(ValueError, match='범위'):
        c.parse_response('[{"n":1,"cites":true},{"n":9,"cites":true}]', 2)


def test_duplicate_index_is_rejected():
    with pytest.raises(ValueError, match='중복'):
        c.parse_response('[{"n":1,"cites":true},{"n":1,"cites":false}]', 2)


def test_missing_cites_field_is_rejected():
    # cites 가 없을 때 bool(None) 로 떨어지면 '인용 아님' 이 조용히 만들어진다.
    with pytest.raises(ValueError, match='cites'):
        c.parse_response('[{"n":1,"why":"…"}]', 1)


def test_non_json_is_an_error():
    with pytest.raises(ValueError, match='JSON'):
        c.parse_response('판정할 수 없습니다', 1)


def test_judge_batches_and_renumbers_to_the_whole_list():
    arts = [{'press': 'p', 'title': f't{i}', 'desc': ''} for i in range(1, 26)]
    seen = []

    def fake(prompt):
        n = prompt.count('\n   ')          # 배치에 실린 기사 수
        seen.append(n)
        return json.dumps([{'n': i, 'cites': True} for i in range(1, n + 1)])

    got = c.judge('제목', '2026-09-07', '요지', arts, call=fake, log=lambda _: None)
    assert seen == [c.BATCH, len(arts) - c.BATCH]
    assert [v.n for v in got] == list(range(1, 26))


def test_provider_prefers_anthropic_then_openrouter_then_none(monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    assert c.provider() is None

    monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-x')
    url, model, headers = c.provider()
    assert 'openrouter' in url and headers['Authorization'] == 'Bearer sk-or-x'

    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-x')
    url, model, headers = c.provider()
    assert 'anthropic.com' in url and headers['x-api-key'] == 'sk-ant-x'


def test_blank_key_is_treated_as_absent(monkeypatch):
    # 워크플로가 시크릿을 안 넣으면 빈 문자열이 들어온다 — 있는 것처럼 굴면
    # 401 을 받고 회차 전체가 판정 없이 끝난다.
    monkeypatch.setenv('ANTHROPIC_API_KEY', '   ')
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    assert c.provider() is None
