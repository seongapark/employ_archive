"""초록·목차·전망근거·카탈로그 설명을 FTS 색인 행으로 옮긴다.

네트워크에 나가지 않는다 — 저장소의 정본 JSON 만 읽는다.
"""
from tools import fts_load


# ── 공백 지우기: 색인과 질의 양쪽에서 같은 규칙이어야 한다 ──────────────────

def test_the_index_copy_has_no_whitespace():
    # trigram 은 공백까지 그대로 맞아야 걸린다(2026-09-10 실물 D1 실측).
    # 색인 사본에서 공백을 지워야 "청년고용" 과 "청년 고용" 이 하나가 된다.
    assert fts_load.squash(' 청년 고용\n실태 ') == '청년고용실태'
    assert fts_load.squash(None) == ''


# ── 청크: 스니펫으로 보여줄 수 있는 크기여야 한다 ──────────────────────────

def test_a_long_abstract_is_split_into_rows_under_the_limit():
    # 초록 한 건이 6천 자다. 통째로 한 행에 넣으면 스니펫을 낼 수가 없다.
    long = '청년 고용률이 하락했다. ' * 300
    out = fts_load.chunks(long, limit=2000)
    assert len(out) > 1
    assert all(len(c) <= 2000 for c in out)
    assert ''.join(out).replace(' ', '') == long.replace(' ', '')


def test_chunks_break_at_sentence_ends():
    # 상한까지 문장을 채워 담되, 끊는 자리는 언제나 문장 끝이다 —
    # 낱말 중간에서 끊기면 스니펫이 읽히지 않는다.
    text = '첫 문장이다. 두 번째 문장이다. 세 번째 문장이다.'
    out = fts_load.chunks(text, limit=20)
    assert len(out) > 1
    assert all(len(c) <= 20 for c in out), out
    assert all(c.endswith('다.') for c in out), out


def test_a_sentence_longer_than_the_limit_is_still_cut():
    # 문장 부호가 없는 글(목차를 이어 붙인 것 등)이 실제로 있다. 한 행이 무한정
    # 길어지면 D1 문장 크기 제한에 걸린다.
    out = fts_load.chunks('가' * 5000, limit=2000)
    assert out and all(len(c) <= 2000 for c in out)


def test_empty_text_yields_no_chunk():
    assert fts_load.chunks('', limit=2000) == []
    assert fts_load.chunks('   ', limit=2000) == []


# ── 행 만들기: 저장소의 실제 데이터에서 ────────────────────────────────────

def test_rows_come_from_all_four_kinds():
    rows = fts_load.rows()
    kinds = {r['종류'] for r in rows}
    assert {'초록', '목차', '전망근거', '충돌', '한계'} <= kinds, sorted(kinds)


def test_every_row_id_is_unique():
    # 중복 id 가 있으면 무엇이 무엇을 덮었는지 알 수 없다.
    ids = [r['doc_id'] for r in fts_load.rows()]
    assert len(ids) == len(set(ids))


def test_every_row_carries_its_domain_and_an_index_copy():
    for r in fts_load.rows():
        assert r['도메인'] in {'reports', 'forecast', 'catalog'}, r['doc_id']
        assert r['본문'], r['doc_id']
        assert r['본문색인'] == fts_load.squash(r['본문']), r['doc_id']
        assert r['제목색인'] == fts_load.squash(r['제목']), r['doc_id']


def test_report_rows_carry_the_institution_link():
    # 이 기능의 목적이 "가서 보라" 이므로 링크 없는 행은 쓸모가 절반이다.
    rows = [r for r in fts_load.rows() if r['도메인'] == 'reports']
    assert rows
    assert all(r['링크'] for r in rows[:50])


def test_reports_without_an_abstract_still_give_their_toc():
    # 초록이 없는 보고서가 257건이다. 목차라도 걸려야 한다.
    rows = fts_load.rows()
    초록 = {r['doc_id'].split(':')[1] for r in rows if r['종류'] == '초록'}
    목차 = {r['doc_id'].split(':')[1] for r in rows if r['종류'] == '목차'}
    assert 목차 - 초록, '초록 없이 목차만 있는 보고서가 하나도 안 나왔다'


# ── SQL: 재실행 가능해야 한다 ──────────────────────────────────────────────

ONE = {'doc_id': 'x', '도메인': 'reports', '종류': '초록', '링크': 'https://x',
       '제목': '제목', '본문': '본문', '제목색인': '제목', '본문색인': '본문'}


def test_the_sql_clears_before_inserting_so_it_can_be_rerun():
    # FTS5 가상표는 ON CONFLICT 를 못 받는다 — upsert 대신 비우고 다시 넣는다.
    sql = fts_load.build_sql([ONE])
    assert sql.startswith('DELETE FROM doc_fts;')
    assert 'INSERT INTO doc_fts' in sql


def test_rows_are_batched_instead_of_one_statement_each():
    sql = fts_load.build_sql([dict(ONE, doc_id=f'x{i}') for i in range(450)], batch=200)
    assert sql.count('INSERT INTO doc_fts') == 3


def test_no_statement_exceeds_the_d1_limit():
    # D1 은 한 문장이 100KB 를 넘으면 거부한다.
    big = dict(ONE, 본문='가' * 2000, 본문색인='가' * 2000)
    sql = fts_load.build_sql([dict(big, doc_id=f'x{i}') for i in range(200)], batch=200)
    assert all(len(s.encode('utf-8')) < 100_000 for s in sql.split(';\n') if s.strip())


def test_a_quote_in_the_text_does_not_break_the_sql():
    sql = fts_load.build_sql([dict(ONE, 제목="따옴표'가 든 제목")])
    assert "따옴표''가" in sql
