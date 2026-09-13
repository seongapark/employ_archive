"""문장 나누기와 묶기. 네트워크에 나가지 않는다."""
import json

import pytest

from tools import d1_push


def test_statements_are_split_on_the_terminator_we_wrote(tmp_path):
    # `fts_load` 가 `;\n` 으로 문장을 끝내며 파일을 쓴다. 같은 규칙으로 나눈다 —
    # 추측이 들어갈 자리가 없다(wrangler 의 추측이 문장을 버렸다).
    (tmp_path / 'a.sql').write_text("DELETE FROM doc_fts;\n", encoding='utf-8')
    (tmp_path / 'b.sql').write_text("INSERT INTO t VALUES ('가;나');\nINSERT INTO t VALUES ('다');\n",
                                    encoding='utf-8')
    stmts = d1_push.statements([tmp_path / 'a.sql', tmp_path / 'b.sql'])
    assert len(stmts) == 3
    # 문장 안의 세미콜론은 경계가 아니다 — 뒤에 줄바꿈이 없다.
    assert "'가;나'" in stmts[1]


def test_statements_keep_their_inner_semicolons_intact(tmp_path):
    # **한 요청에 한 문장만 보내는 이유.** 여러 문장을 한 sql 에 담아 보냈더니 D1 이 글
    # 안의 세미콜론을 문장 경계로 읽고 넘어졌다(unrecognized token). 문장은 안 쪼갠다.
    한글 = "INSERT INTO t VALUES ('가; 나');\nINSERT INTO t VALUES ('다');\n"
    (tmp_path / 'a.sql').write_text(한글, encoding='utf-8')
    stmts = d1_push.statements([tmp_path / 'a.sql'])
    assert len(stmts) == 2
    assert "'가; 나'" in stmts[0]


def test_database_id_comes_from_the_wrangler_config():
    # 두 벌로 적지 않는다 — 설정이 정본이다.
    assert len(d1_push.database_id()) == 36


def test_an_api_failure_is_loud():
    # 조용한 실패가 이 저장소를 두 번 물었다. 성공 플래그가 거짓이면 터진다.
    class _Res:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({'success': False, 'errors': [{'message': '못 한다'}]}).encode()

    with pytest.raises(SystemExit):
        d1_push.post('SELECT 1;', account='a', db='b', token='t', opener=lambda *a, **k: _Res())
