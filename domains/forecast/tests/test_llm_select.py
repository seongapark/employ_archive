import json

import pytest
import requests

from domains.forecast.pipeline import llm_select as s

PAGES = ["표지", "2026년 취업자는 내수 회복으로 늘어날 전망", "각주"]


def test_prompt_carries_page_numbers_so_the_model_can_cite():
    p = s.build_prompt("KDI", "KDI 경제전망 2026", ["emp_change"], PAGES)
    assert "1쪽" in p and "2쪽" in p and "3쪽" in p
    assert "2026년 취업자는 내수 회복으로 늘어날 전망" in p


def test_prompt_names_only_the_indicators_this_org_forecasts():
    # 인디케이터 목록 전체가 실제로 프롬프트에 실리는지(하나만 하드코딩된 게 아닌지),
    # 그리고 목록에 없는 그럴듯한 지표는 섞여 들어오지 않는지를 함께 확인한다.
    p = s.build_prompt("KLI", "노동리뷰", ["emp_change", "unemployment_rate", "cpi"], PAGES)
    assert "emp_change" in p and "unemployment_rate" in p and "cpi" in p
    assert "gdp_growth" not in p


def test_prompt_forbids_rewriting():
    p = s.build_prompt("KDI", "t", ["cpi"], PAGES)
    assert "한 글자도" in p


def test_parse_reads_the_json_array():
    body = json.dumps([{"indicator": "emp_change", "text": "가나다", "source_page": 2}],
                      ensure_ascii=False)
    assert s.parse_response(body) == [s.Picked("emp_change", "가나다", 2)]


def test_parse_tolerates_a_fenced_code_block():
    body = "```json\n[{\"indicator\":\"cpi\",\"text\":\"가\",\"source_page\":1}]\n```"
    assert s.parse_response(body) == [s.Picked("cpi", "가", 1)]


def test_parse_drops_an_entry_with_an_empty_text():
    body = json.dumps([{"indicator": "cpi", "text": "", "source_page": 1}])
    assert s.parse_response(body) == []


def test_parse_raises_on_unparsable_output():
    with pytest.raises(ValueError):
        s.parse_response("죄송합니다, 찾지 못했습니다")


def test_parse_raises_a_named_error_when_indicator_is_missing():
    body = json.dumps([{"text": "가나다", "source_page": 1}], ensure_ascii=False)
    with pytest.raises(ValueError):
        s.parse_response(body)


def test_parse_raises_a_named_error_when_source_page_is_missing():
    body = json.dumps([{"indicator": "cpi", "text": "가나다"}], ensure_ascii=False)
    with pytest.raises(ValueError):
        s.parse_response(body)


def test_parse_raises_a_named_error_when_source_page_is_null():
    body = json.dumps([{"indicator": "cpi", "text": "가나다", "source_page": None}],
                      ensure_ascii=False)
    with pytest.raises(ValueError):
        s.parse_response(body)


def test_parse_raises_a_named_error_when_source_page_is_a_list():
    body = json.dumps([{"indicator": "cpi", "text": "가나다", "source_page": [1, 2]}],
                      ensure_ascii=False)
    with pytest.raises(ValueError):
        s.parse_response(body)


def test_parse_raises_a_named_error_when_rows_are_not_objects():
    body = json.dumps(["가나다", "라마바"], ensure_ascii=False)
    with pytest.raises(ValueError):
        s.parse_response(body)


def test_parse_rejects_source_page_zero_so_it_cannot_wrap_to_the_last_page():
    # pages[source_page - 1] 로 색인하므로 0 은 pages[-1](마지막 쪽)로 둔갑한다.
    # 잘못된 쪽과 대조해 통과해버리는 사고를 막기 위해 여기서 막아야 한다.
    body = json.dumps([{"indicator": "cpi", "text": "가나다", "source_page": 0}],
                      ensure_ascii=False)
    with pytest.raises(ValueError):
        s.parse_response(body)


def test_parse_rejects_a_negative_source_page():
    body = json.dumps([{"indicator": "cpi", "text": "가나다", "source_page": -1}],
                      ensure_ascii=False)
    with pytest.raises(ValueError):
        s.parse_response(body)


def test_parse_raises_a_named_error_on_an_infinite_source_page():
    # json.dumps/json.loads 는 기본값으로 Infinity 를 그대로 주고받는다.
    # int(float("inf")) 는 OverflowError 를 던지므로 이것도 잡아야 한다.
    body = json.dumps([{"indicator": "cpi", "text": "가나다", "source_page": float("inf")}],
                      ensure_ascii=False)
    with pytest.raises(ValueError):
        s.parse_response(body)


def test_parse_raises_a_named_error_when_indicator_is_null():
    # str(None) 이 "None" 으로 둔갑해 지표 이름처럼 보이면 안 된다.
    body = json.dumps([{"indicator": None, "text": "가나다", "source_page": 1}],
                      ensure_ascii=False)
    with pytest.raises(ValueError):
        s.parse_response(body)


class _FakeResponse:
    """requests.Response 를 흉내낸다 — 네트워크는 전혀 열지 않는다."""

    def __init__(self, status_code=200, json_body=None, text=""):
        self.status_code = status_code
        self._json_body = json_body
        self.text = text

    def json(self):
        if self._json_body is None:
            raise json.JSONDecodeError("no body", "", 0)
        return self._json_body

    def raise_for_status(self):
        # 진짜 requests.Response 처럼 400 미만은 그냥 넘어가고, 그 이상은
        # HTTPError 를 던진다 — 이 흉내가 부실하면 뮤테이션 테스트가
        # "가짜가 부실해서" 실패하는 거짓 신호를 준다.
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)


def test_call_api_posts_the_expected_shape_to_the_messages_endpoint(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _FakeResponse(200, {"content": [{"text": "가나다"}]})

    monkeypatch.setattr(s.requests, "post", fake_post)

    got = s._call_api("프롬프트-내용")

    assert got == "가나다"
    # 모듈 상수가 아니라 리터럴과 대조한다 — 상수 자체가 오타나면
    # s.API_URL/s.MODEL 과 비교해서는 절대 잡지 못한다.
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert set(captured["headers"]) == {"x-api-key", "anthropic-version", "content-type"}
    assert captured["headers"]["x-api-key"] == "sk-test-key"
    assert captured["json"]["model"] == "claude-sonnet-5"
    assert captured["json"]["messages"][0]["content"] == "프롬프트-내용"


def test_call_api_raises_when_both_keys_are_missing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        s._call_api("x")


def test_call_api_falls_back_to_openrouter_when_only_that_key_is_set(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        # OpenAI 호환 응답 — Anthropic 의 content 배열이 아니다.
        return _FakeResponse(200, {"choices": [{"message": {"content": "가나다"}}]})

    monkeypatch.setattr(s.requests, "post", fake_post)

    assert s._call_api("프롬프트-내용") == "가나다"
    # 모듈 상수가 아니라 리터럴과 대조한다(위 테스트와 같은 이유).
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-or-test"
    assert "x-api-key" not in captured["headers"]
    assert captured["json"]["model"] == "anthropic/claude-sonnet-5"
    assert captured["json"]["messages"][0]["content"] == "프롬프트-내용"


def test_anthropic_wins_when_both_keys_are_set(monkeypatch):
    """공급자 차례를 고정한다 — press 의 llm_cite 와 같아야 한다."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    url, model, headers = s.provider()
    assert url == "https://api.anthropic.com/v1/messages"
    assert model == "claude-sonnet-5"
    assert headers["x-api-key"] == "sk-test-key"


def test_call_api_raises_on_a_non_200_and_keeps_the_body_text(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

    def fake_post(*a, **kw):
        return _FakeResponse(401, text='{"error": {"message": "invalid x-api-key"}}')

    monkeypatch.setattr(s.requests, "post", fake_post)

    with pytest.raises(ValueError) as e:
        s._call_api("x")
    assert "invalid x-api-key" in str(e.value)


def test_call_api_raises_on_a_200_with_an_unexpected_body(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

    def fake_post(*a, **kw):
        return _FakeResponse(200, {"unexpected": "shape"})

    monkeypatch.setattr(s.requests, "post", fake_post)

    with pytest.raises(ValueError):
        s._call_api("x")


def test_select_uses_the_injected_call_and_does_not_touch_the_network():
    seen = {}

    def fake(prompt):
        seen["prompt"] = prompt
        return json.dumps([{"indicator": "emp_change", "text": "가", "source_page": 2}],
                          ensure_ascii=False)

    got = s.select("KDI", "t", ["emp_change"], PAGES, call=fake)
    assert got == [s.Picked("emp_change", "가", 2)]
    assert "KDI" in seen["prompt"]


def test_call_api_raises_a_named_error_when_the_content_is_null(monkeypatch):
    """추론 토큰이 max_tokens 를 다 먹으면 OpenRouter 는 content 를 null 로
    돌려준다. 그대로 넘기면 parse_response 에서 'NoneType has no attribute
    strip' 이 나서, 실행 로그만 보고는 무엇이 잘못됐는지 알 수 없다."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    body = {"choices": [{"finish_reason": "length", "message": {"content": None}}]}

    def fake_post(*a, **kw):
        # 진짜 Response 는 .text 가 본문 그대로다 — 가짜도 그래야 오류
        # 메시지가 본문을 싣는지 정직하게 확인할 수 있다.
        return _FakeResponse(200, body, text=json.dumps(body))

    monkeypatch.setattr(s.requests, "post", fake_post)

    with pytest.raises(ValueError) as e:
        s._call_api("x")
    assert "length" in str(e.value)   # 본문을 실어 보내 원인을 알 수 있어야 한다


def test_parse_reads_an_array_behind_a_bare_json_prefix():
    """실측: 백틱 없이 "json" 한 줄만 앞에 붙어 온 회차가 있었다(BOK 2026년
    5월). 형식이 실행마다 흔들리는데 그때마다 그 회차가 통째로 죽었다."""
    body = 'json\n[{"indicator": "cpi", "text": "가", "source_page": 2}]'
    assert s.parse_response(body) == [s.Picked("cpi", "가", 2)]


def test_parse_reads_an_array_behind_a_sentence():
    body = '다음과 같습니다:\n\n[{"indicator": "cpi", "text": "가", "source_page": 2}]'
    assert s.parse_response(body) == [s.Picked("cpi", "가", 2)]


def test_parse_still_raises_when_there_is_no_array_at_all():
    with pytest.raises(ValueError):
        s.parse_response("죄송합니다, 근거를 찾지 못했습니다.")


def test_call_api_pins_the_temperature_so_reruns_reproduce(monkeypatch):
    """정하지 않으면 기본 샘플링이라 같은 입력에 매번 다른 답이 온다 —
    쪽번호가 24와 23 사이를 오갔고, 응답 형식조차 실행마다 달랐다(백틱 없는
    "json" 접두어로 한 회차가 죽었다). 실측: temperature 0 이면 같은 입력에
    글자까지 같은 답이 온다(2회 확인, 추론을 켠 채로도 받아들여진다)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(json)
        return _FakeResponse(200, {"content": [{"text": "가"}]})

    monkeypatch.setattr(s.requests, "post", fake_post)
    s._call_api("x")

    assert captured["temperature"] == 0


def test_provider_는_openai_를_마지막에_쓴다(monkeypatch):
    # 차례가 뒤집히면 이미 쌓인 근거(claude-sonnet-5 가 고른 문장)와
    # 앞으로 쌓일 근거의 선별자가 회차마다 갈린다.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    monkeypatch.setenv("OPENROUTER_API_KEY", "o")
    monkeypatch.setenv("OPENAI_API_KEY", "p")
    assert s.provider()[0] == s.ANTHROPIC_URL

    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert s.provider()[0] == s.OPENROUTER_URL

    monkeypatch.delenv("OPENROUTER_API_KEY")
    url, model, headers = s.provider()
    assert url == s.OPENAI_URL
    assert model == s.MODEL_OPENAI
    assert headers["Authorization"] == "Bearer p"

    monkeypatch.delenv("OPENAI_API_KEY")
    assert s.provider() is None


# ── 구독(Claude Code CLI)으로 문장 고르기 ───────────────────────────────────
# API 크레딧을 채우지 않고 Pro/Max 구독으로 돌리는 경로. HTTP 가 아니라
# `claude -p` 를 부르므로 provider() 의 url 자리에 센티넬이 들어가고 headers 는
# 빈 dict 다. reports 의 recommend.py 와 같은 스위치(JUDGE_PROVIDER)를 쓴다.

def test_the_cli_switch_wins_over_every_api_key(monkeypatch):
    # 구독으로 돌리려고 켠 스위치가 API 키에 밀리면, 잔액 0 인 키로 돌다가
    # 크레딧 부족으로 죽는다 — 구독으로 돌고 있다고 착각하기 가장 쉬운 실패다.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-zero-balance")
    monkeypatch.setenv("JUDGE_PROVIDER", "cli")
    url, model, headers = s.provider()
    assert url == s.CLI_URL
    assert model == s.MODEL_ANTHROPIC
    assert headers == {}


def test_without_the_switch_the_key_order_is_unchanged(monkeypatch):
    # 스위치를 켜지 않으면 기존 세 키 차례가 그대로여야 한다(회귀 방지).
    monkeypatch.delenv("JUDGE_PROVIDER", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    url, _, headers = s.provider()
    assert "api.anthropic.com" in url and headers["x-api-key"] == "sk-ant-x"


def _fake_cli(monkeypatch, *, result="[]", returncode=0, stderr=""):
    """subprocess.run 을 가로채고 argv·env·stdin 을 돌려준다."""
    seen = {}

    class Done:
        pass

    def fake_run(argv, **kw):
        seen["argv"] = argv
        seen["env"] = kw.get("env") or {}
        seen["input"] = kw.get("input")
        done = Done()
        done.returncode = returncode
        done.stdout = result if isinstance(result, str) else json.dumps(result)
        done.stderr = stderr
        return done

    monkeypatch.setattr(s.subprocess, "run", fake_run)
    return seen


def test_the_prompt_goes_through_stdin_not_argv(monkeypatch):
    # 이 도구는 보고서 **전문**을 한 번에 준다 — BOK 한 회차가 42,000자(실측)라
    # Windows 명령줄 상한 32,767자를 넘는다. argv 로 되돌리면 큰 회차만 죽는다
    # (작은 KDI 로 시험하면 멀쩡해 보이는 자리다).
    seen = _fake_cli(monkeypatch, result=json.dumps({"result": "[]"}))
    long_prompt = "가" * 40000
    s._call_cli(long_prompt)
    assert seen["input"] == long_prompt
    assert long_prompt not in seen["argv"]


def test_the_cli_call_scrubs_api_keys_from_the_child_env(monkeypatch):
    # `claude -p` 의 인증 우선순위는 ANTHROPIC_API_KEY(3위) >
    # CLAUDE_CODE_OAUTH_TOKEN(5위) 이고, 비대화형(-p)에서는 키가 있으면 **항상**
    # 그걸 쓴다. 잔액 0 키가 환경에 남아 있으면 구독이 아니라 그 키로 돈다.
    seen = _fake_cli(monkeypatch, result=json.dumps({"result": "[]"}))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-zero")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "bearer-x")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oat-live")

    s._call_cli("프롬프트")

    assert "ANTHROPIC_API_KEY" not in seen["env"]
    assert "ANTHROPIC_AUTH_TOKEN" not in seen["env"]
    assert seen["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == "oat-live"


def test_the_cli_call_never_passes_bare(monkeypatch):
    # --bare 는 CLAUDE_CODE_OAUTH_TOKEN 을 안 읽는다 — 붙이면 인증이 통째로 안 된다.
    seen = _fake_cli(monkeypatch, result=json.dumps({"result": "[]"}))
    s._call_cli("프롬프트")
    assert "--bare" not in seen["argv"]
    assert "-p" in seen["argv"]


def test_the_cli_call_unwraps_the_json_envelope(monkeypatch):
    # --output-format json 은 답을 봉투에 담아 준다. 봉투째 넘기면 parse_response
    # 가 근거 배열이 아니라 봉투의 키들을 읽으려 한다.
    body = json.dumps([{"indicator": "emp_change", "text": "내수가 회복된다",
                        "source_page": 2}], ensure_ascii=False)
    _fake_cli(monkeypatch, result=json.dumps({"type": "result", "is_error": False,
                                              "result": body}))
    assert s._call_cli("프롬프트") == body


def test_a_failing_cli_raises_instead_of_returning_nothing(monkeypatch):
    # 조용히 빈 문자열을 돌려주면 그 회차가 '근거 없음' 으로 지나간다.
    # 헤드리스 OAuth 토큰은 10~15분이면 만료된다 — 긴 배치에서 실제로 난다.
    _fake_cli(monkeypatch, result="", returncode=1,
              stderr="OAuth token has expired")
    with pytest.raises(ValueError) as got:
        s._call_cli("프롬프트")
    assert "OAuth token has expired" in str(got.value)


def test_call_api_routes_the_cli_provider_to_the_cli(monkeypatch):
    # provider() 가 센티넬 url 을 돌려줬는데 _call_api 가 그걸 requests.post 에
    # 넘기면 cli:// 로 HTTP 를 치려 한다.
    monkeypatch.setenv("JUDGE_PROVIDER", "cli")
    _fake_cli(monkeypatch, result=json.dumps({"result": "ok"}))
    monkeypatch.setattr(s.requests, "post",
                        lambda *a, **k: pytest.fail("CLI 경로가 HTTP 를 쳤다"))
    assert s._call_api("프롬프트") == "ok"


def test_the_cli_model_can_be_swapped(monkeypatch):
    # Pro 요금제는 Opus 사용이 제한될 수 있다. provider() 와 _call_cli 가 같은
    # 값을 봐야 보고서에 적히는 모델 이름이 거짓이 되지 않는다.
    monkeypatch.setenv("JUDGE_PROVIDER", "cli")
    monkeypatch.setenv("JUDGE_CLI_MODEL", "claude-haiku-4-5-20251001")
    seen = _fake_cli(monkeypatch, result=json.dumps({"result": "[]"}))
    _, model, _ = s.provider()
    s._call_cli("프롬프트")
    assert model == "claude-haiku-4-5-20251001"
    assert seen["argv"][seen["argv"].index("--model") + 1] == model
