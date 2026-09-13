# -*- coding: utf-8 -*-
"""질의응답 현황 기록. 관리자 화면의 유일한 감시 값이라 **지어내면 안 된다**."""
import json
from datetime import datetime, timedelta, timezone

from tools import ask_stamp

KST = timezone(timedelta(hours=9))
찬색인 = {'reports': 3000, 'forecast': 60, 'press': 200, 'catalog': 526}


def test_성공한_적재는_정상으로_기록된다():
    d = ask_stamp.기록(찬색인, ok=True, now=datetime(2026, 9, 13, 12, 0, tzinfo=KST))
    assert d['run_at'] == '2026-09-13T12:00:00+09:00'
    assert d['catalog']['ok'] is True
    assert d['catalog']['rows'] == 526
    assert d['fts']['rows'] == 3786


def test_앞단계가_실패하면_정상이라고_적지_않는다():
    # 실패한 회차도 기록은 남긴다 — 안 남기면 화면은 '오래됐다' 라고만 하고
    # 무엇이 틀렸는지 말하지 못한다.
    d = ask_stamp.기록(찬색인, ok=False)
    assert d['catalog']['ok'] is False


def test_한_도메인이라도_비면_실패다():
    # 적재가 조용히 반만 되는 실패가 실제로 있었다(tools/fts_verify.py).
    # 앞 단계가 초록이어도 건수가 그 사실을 뒤집는다.
    d = ask_stamp.기록({**찬색인, 'press': 0}, ok=True)
    assert d['catalog']['ok'] is False
    assert d['catalog']['빈도메인'] == ['press']


def test_counts_가_없으면_0건_실패로_남는다(tmp_path):
    # 적재기가 먼저 죽으면 counts.json 이 없다.
    out = tmp_path / 'last_run.json'
    ask_stamp.main(['--status', 'failure', '--out', str(out)])
    d = json.loads(out.read_text(encoding='utf-8'))
    assert d['catalog']['ok'] is False and d['fts']['rows'] == 0


def test_관리자_어댑터가_요구하는_필드를_지킨다(tmp_path):
    # domains/admin/app/js/model.js 의 어댑터_ask 는 run_at(문자열)과
    # catalog.ok(불리언)를 요구한다. 이름이 바뀌면 카드가 '형식오류' 가 된다.
    counts = tmp_path / 'counts.json'
    counts.write_text(json.dumps(찬색인), encoding='utf-8')
    out = tmp_path / 'last_run.json'
    ask_stamp.main([str(counts), '--out', str(out)])
    d = json.loads(out.read_text(encoding='utf-8'))
    assert isinstance(d['run_at'], str) and isinstance(d['catalog']['ok'], bool)
