import json

import pytest

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
    assert captured["url"] == s.API_URL
    assert set(captured["headers"]) == {"x-api-key", "anthropic-version", "content-type"}
    assert captured["headers"]["x-api-key"] == "sk-test-key"
    assert captured["json"]["model"] == s.MODEL
    assert captured["json"]["messages"][0]["content"] == "프롬프트-내용"


def test_call_api_raises_when_the_key_is_missing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        s._call_api("x")


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
