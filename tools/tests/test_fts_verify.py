"""적재가 반만 된 것을 잡는 확인기. 네트워크에 나가지 않는다."""
import json

import pytest

from tools import fts_verify


def test_counts_are_read_from_the_wrangler_json_shape():
    payload = json.dumps([{'results': [{'도메인': 'reports', 'n': 4282},
                                       {'도메인': 'press', 'n': 329}],
                           'success': True}])
    assert fts_verify.건수(payload) == {'reports': 4282, 'press': 329}


def test_an_empty_result_is_a_failure_not_a_zero():
    # 확인기가 확인을 못 하는 것이 가장 나쁘다 — 조용히 0건으로 읽지 않는다.
    with pytest.raises(SystemExit):
        fts_verify.건수(json.dumps([{'results': [], 'success': True}]))


def test_a_short_load_fails_even_when_no_domain_is_empty(monkeypatch, capsys, tmp_path):
    # 두 번째 실패가 이 모양이었다 — 네 도메인 다 있는데 reports 만 202행 모자랐다.
    예상 = tmp_path / 'counts.json'
    예상.write_text('{"reports": 4853, "forecast": 166, "press": 329, "catalog": 31}',
                   encoding='utf-8')
    rows = [{'도메인': 'reports', 'n': 4651}, {'도메인': 'forecast', 'n': 166},
            {'도메인': 'press', 'n': 329}, {'도메인': 'catalog', 'n': 31}]
    monkeypatch.setattr('sys.stdin', _Stdin(json.dumps([{'results': rows}])))
    assert fts_verify.main([str(예상)]) == 1
    assert '4651행만' in capsys.readouterr().err


def test_a_missing_domain_fails(monkeypatch, capsys):
    # 2026-09-13 의 실패가 정확히 이 모양이었다: reports 만 남고 나머지가 사라졌다.
    payload = json.dumps([{'results': [{'도메인': 'reports', 'n': 4282}]}])
    monkeypatch.setattr('sys.stdin', _Stdin(payload))
    assert fts_verify.main([]) == 1
    assert '비었다' in capsys.readouterr().err


def test_all_four_domains_pass(monkeypatch):
    rows = [{'도메인': d, 'n': 1} for d in fts_verify.필수]
    monkeypatch.setattr('sys.stdin', _Stdin(json.dumps([{'results': rows}])))
    assert fts_verify.main([]) == 0


class _Stdin:
    def __init__(self, text):
        self._text = text

    def read(self):
        return self._text
