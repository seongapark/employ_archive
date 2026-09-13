"""**생성한 SQL 을 실제로 파싱해 본다.** 네트워크에 나가지 않는다 — D1 도 SQLite 다.

이 검사가 없어서 하루에 여섯 번을 헛돌았다. 적재가 조용히 반만 되거나(wrangler 의
`leftover buffer`, 종료코드 0) 원격에서 400 이 났는데, 원인은 전부 **문장 자체가
SQLite 에 안 먹는 것**이었다(본문에 든 NUL·주석 표시·줄바꿈). 여기서 한 번 실행해
보면 CI 를 태우기 전에 그 자리에서 잡힌다.
"""
from __future__ import annotations

import sqlite3

from tools import d1_push, fts_load

MIGRATION = 'domains/ask/worker/migrations/0005_fts_date.sql'


def _db():
    db = sqlite3.connect(':memory:')
    with open(MIGRATION, encoding='utf-8') as f:
        db.executescript(f.read())
    return db


def test_every_generated_statement_parses_and_runs(tmp_path):
    fts_load.write_files(tmp_path)
    stmts = d1_push.statements(sorted(tmp_path.glob('*.sql')))
    assert len(stmts) > 10, stmts
    db = _db()
    for s in stmts:
        db.execute(s)                      # 안 먹으면 여기서 터진다
    count = db.execute('SELECT COUNT(*) FROM doc_fts').fetchone()[0]
    assert count == sum(fts_load.rows_per_domain().values()), count


def test_control_characters_are_stripped():
    # 초록 본문에 NUL 이 들어 있었다(PDF 에서 뽑은 글). SQLite 는 NUL 이 든 질의를
    # 거부하고, D1 은 그 자리에서 문자열이 끝난 것처럼 읽어 unrecognized token 을 낸다.
    assert fts_load.plain('가\x00나\x07다') == '가 나 다'
    for r in fts_load.rows():
        for c in ('제목', '본문', '제목색인', '본문색인'):
            assert '\x00' not in r[c], (r['doc_id'], c)
