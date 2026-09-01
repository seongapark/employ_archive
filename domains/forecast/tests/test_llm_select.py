import json

import pytest

from domains.forecast.pipeline import llm_select as s

PAGES = ["표지", "2026년 취업자는 내수 회복으로 늘어날 전망", "각주"]


def test_prompt_carries_page_numbers_so_the_model_can_cite():
    p = s.build_prompt("KDI", "KDI 경제전망 2026", ["emp_change"], PAGES)
    assert "1쪽" in p and "2쪽" in p and "3쪽" in p
    assert "2026년 취업자는 내수 회복으로 늘어날 전망" in p


def test_prompt_names_only_the_indicators_this_org_forecasts():
    p = s.build_prompt("KLI", "노동리뷰", ["emp_change"], PAGES)
    assert "emp_change" in p
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


def test_select_uses_the_injected_call_and_does_not_touch_the_network():
    seen = {}

    def fake(prompt):
        seen["prompt"] = prompt
        return json.dumps([{"indicator": "emp_change", "text": "가", "source_page": 2}],
                          ensure_ascii=False)

    got = s.select("KDI", "t", ["emp_change"], PAGES, call=fake)
    assert got == [s.Picked("emp_change", "가", 2)]
    assert "KDI" in seen["prompt"]
