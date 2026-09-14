"""같은 내용을 D1 에 다시 밀지 않는다.

  python -m tools.d1_gate check  <키> <sql파일...>   # push | skip 을 찍는다
  python -m tools.d1_gate record <키> <sql파일...>   # 적재·검증이 끝난 뒤 도장

**왜 필요한가.** 적재기 둘 다 내용이 그대로여도 전량을 다시 쓴다. `d1_sync` 는
모든 행에 `INSERT ... ON CONFLICT DO UPDATE` 를 내고, `fts_load` 는 FTS5 가
upsert 를 못 받아 `DELETE` 후 전량 INSERT 한다. D1 은 값이 같아도 쓰기로 세므로,
아무것도 안 바뀐 날에도 고용동향 8,823행이 나간다 — 그런 날이 대부분이다(평소
수집 커밋은 `last_run.json` 한 줄만 바꾸는데, `d1_sync` 는 그 파일을 읽지도
않는다). 2026-09-13 에 하루 쓰기 10만행 한도를 넘겼다.

**지문을 D1 에 둔다. 저장소가 아니라.** 지문이 답해야 하는 질문은 "파일이
바뀌었나"가 아니라 **"저 DB 에 이미 이 내용이 들어 있나"** 다. 저장소에 적으면
적재가 반만 들어간 회차 뒤에 둘이 어긋나고, 그때 건너뛰면 깨진 채로 굳는다.
적재와 검증이 **끝난 뒤에만** 도장을 찍으므로, 지문이 있다는 것 자체가 그
내용으로 한 번 성공했다는 기록이다.

**막힐 때는 열어 준다.** 지문을 못 읽으면 `push` 다. 게이트가 고장 나서 적재가
멈추는 것이 같은 내용을 한 번 더 쓰는 것보다 나쁘다.
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import sys
from datetime import datetime, timezone

from .d1_push import database_id, post

TABLE = 'sync_state'
DDL = (f'CREATE TABLE IF NOT EXISTS {TABLE} '
       '(키 TEXT PRIMARY KEY, 지문 TEXT NOT NULL, 시각 TEXT NOT NULL)')


def digest(paths) -> str:
    """밀어 넣을 SQL 그대로의 지문. 파일 순서까지 내용의 일부다(DELETE 가 앞)."""
    h = hashlib.sha256()
    for p in paths:
        h.update(pathlib.Path(p).read_bytes())
    return h.hexdigest()


def _sql_quote(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def _conn():
    token = os.environ.get('CLOUDFLARE_API_TOKEN')
    account = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
    if not token or not account:
        raise SystemExit('CLOUDFLARE_API_TOKEN·CLOUDFLARE_ACCOUNT_ID 가 필요하다')
    return {'account': account, 'db': database_id(), 'token': token}


def stored(키: str, *, conn=None, send=post) -> str | None:
    """D1 에 적힌 지문. 표가 없으면 만들고 None 을 준다."""
    c = conn or _conn()
    send(DDL, **c)
    body = send(f'SELECT 지문 FROM {TABLE} WHERE 키 = {_sql_quote(키)}', **c)
    for block in body.get('result') or []:
        for row in block.get('results') or []:
            return row.get('지문')
    return None


def record(키: str, 지문: str, *, conn=None, send=post, now=None) -> None:
    """적재와 검증이 끝난 뒤에만 부른다."""
    c = conn or _conn()
    시각 = (now or datetime.now(timezone.utc)).isoformat(timespec='seconds')
    send(DDL, **c)
    send(f'INSERT INTO {TABLE} (키, 지문, 시각) VALUES '
         f'({_sql_quote(키)}, {_sql_quote(지문)}, {_sql_quote(시각)}) '
         f'ON CONFLICT(키) DO UPDATE SET 지문 = excluded.지문, 시각 = excluded.시각', **c)


def check(키: str, paths, *, conn=None, send=post, log=None) -> str:
    """'push' 또는 'skip'. 판단이 안 서면 'push' 다."""
    말하기 = log or (lambda m: print(m, file=sys.stderr))
    지문 = digest(paths)
    try:
        옛것 = stored(키, conn=conn, send=send)
    except SystemExit as exc:
        말하기(f'{키}: 지문을 못 읽었다({exc}) — 그냥 민다')
        return 'push'
    if 옛것 == 지문:
        말하기(f'{키}: 내용이 그대로다({지문[:12]}) — 건너뛴다')
        return 'skip'
    말하기(f'{키}: 바뀌었다({(옛것 or "없음")[:12]} → {지문[:12]}) — 민다')
    return 'push'


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 3 or args[0] not in ('check', 'record'):
        raise SystemExit('사용법: python -m tools.d1_gate <check|record> <키> <sql파일...>')
    명령, 키, paths = args[0], args[1], args[2:]
    if 명령 == 'check':
        print(check(키, paths))
        return 0
    record(키, digest(paths))
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    raise SystemExit(main())
