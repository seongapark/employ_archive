"""같은 내용을 다시 밀지 않는 판단. 네트워크에 나가지 않는다."""
import pytest

from tools import d1_gate

CONN = {'account': 'a', 'db': 'b', 'token': 't'}


class 가짜D1:
    """보낸 SQL 을 모으고, SELECT 에는 정해 둔 지문을 돌려준다."""

    def __init__(self, 지문=None, 터진다=False):
        self.지문 = 지문
        self.터진다 = 터진다
        self.보낸것 = []

    def __call__(self, sql, **_):
        self.보낸것.append(sql)
        if self.터진다:
            raise SystemExit('D1 거부 401')
        if sql.startswith('SELECT'):
            결과 = [{'지문': self.지문}] if self.지문 else []
            return {'success': True, 'result': [{'results': 결과}]}
        return {'success': True, 'result': []}


def sql(tmp_path, *내용):
    out = []
    for i, t in enumerate(내용):
        p = tmp_path / f'{i}.sql'
        p.write_text(t, encoding='utf-8')
        out.append(p)
    return out


def test_the_digest_follows_the_bytes_we_are_about_to_push(tmp_path):
    (tmp_path / 'x.sql').write_text('INSERT 1;\n', encoding='utf-8')
    (tmp_path / 'y.sql').write_text('INSERT 1;\n', encoding='utf-8')
    (tmp_path / 'z.sql').write_text('INSERT 2;\n', encoding='utf-8')
    assert d1_gate.digest([tmp_path / 'x.sql']) == d1_gate.digest([tmp_path / 'y.sql'])
    assert d1_gate.digest([tmp_path / 'x.sql']) != d1_gate.digest([tmp_path / 'z.sql'])
    # 파일 순서도 내용의 일부다 — DELETE 가 맨 앞이라야 뜻이 같다.
    앞뒤 = d1_gate.digest([tmp_path / 'x.sql', tmp_path / 'z.sql'])
    뒤앞 = d1_gate.digest([tmp_path / 'z.sql', tmp_path / 'x.sql'])
    assert 앞뒤 != 뒤앞


def test_same_content_is_skipped(tmp_path):
    # 평소 날 수집은 last_run.json 한 줄만 바꾸는데 d1_sync 는 그 파일을 읽지도
    # 않는다. 그래서 SQL 이 어제와 바이트 단위로 같고, 그날 쓰기는 낭비다.
    paths = sql(tmp_path, 'INSERT 1;\n')
    d1 = 가짜D1(지문=d1_gate.digest(paths))
    assert d1_gate.check('employment', paths, conn=CONN, send=d1, log=lambda _: None) == 'skip'


def test_changed_content_is_pushed(tmp_path):
    paths = sql(tmp_path, 'INSERT 1;\n')
    d1 = 가짜D1(지문='옛지문')
    assert d1_gate.check('employment', paths, conn=CONN, send=d1, log=lambda _: None) == 'push'


def test_a_first_run_with_no_stamp_is_pushed(tmp_path):
    paths = sql(tmp_path, 'INSERT 1;\n')
    d1 = 가짜D1(지문=None)
    assert d1_gate.check('fts', paths, conn=CONN, send=d1, log=lambda _: None) == 'push'


def test_the_gate_fails_open(tmp_path):
    # 게이트가 고장 나서 적재가 멈추는 것이, 같은 내용을 한 번 더 쓰는 것보다
    # 나쁘다. 지문을 못 읽으면 민다.
    paths = sql(tmp_path, 'INSERT 1;\n')
    d1 = 가짜D1(터진다=True)
    assert d1_gate.check('fts', paths, conn=CONN, send=d1, log=lambda _: None) == 'push'


def test_the_table_is_created_before_it_is_read(tmp_path):
    # 마이그레이션은 사람이 손으로 돌린다(DEPLOY.md §1-3). 게이트가 그것을
    # 기다리면 배포 다음 첫 회차가 `no such table` 로 죽는다.
    paths = sql(tmp_path, 'INSERT 1;\n')
    d1 = 가짜D1(지문=None)
    d1_gate.check('fts', paths, conn=CONN, send=d1, log=lambda _: None)
    assert d1.보낸것[0].startswith('CREATE TABLE IF NOT EXISTS sync_state')


def test_recording_upserts_the_stamp(tmp_path):
    d1 = 가짜D1()
    d1_gate.record('fts', 'abc123', conn=CONN, send=d1)
    적은것 = [s for s in d1.보낸것 if s.startswith('INSERT INTO sync_state')]
    assert len(적은것) == 1
    assert "'abc123'" in 적은것[0]
    # 두 번째 회차가 같은 키로 다시 찍는다 — 충돌하면 갱신이어야 한다.
    assert 'ON CONFLICT(키) DO UPDATE' in 적은것[0]


@pytest.mark.parametrize('키', ["fts", "o'brien"])
def test_keys_are_quoted_not_interpolated(tmp_path, 키):
    d1 = 가짜D1()
    d1_gate.record(키, 'abc', conn=CONN, send=d1)
    assert "o''brien" in d1.보낸것[-1] or 키 == 'fts'
