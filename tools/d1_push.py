"""SQL 파일을 D1 REST API 로 직접 밀어 넣는다.

  python -m tools.d1_push /tmp/fts/*.sql

**왜 wrangler 를 안 쓰는가.** `wrangler d1 execute --remote --file` 이 파일을 나눠 읽으며
경계에 걸친 문장을 버린다 — `Warning: leftover buffer from sql.ingest` 한 줄을 남기고
**종료코드 0** 으로 끝난다. 2026-09-13 에 조각 크기를 2MB→700KB→400KB 로 줄여 가며 재
봤는데 소실이 202→138→30행으로 줄기만 하고 사라지지 않았다(로컬 적재로는 재현되지
않는다 — 원격 ingest 경로만의 문제다). 조각을 더 줄이는 것은 끝이 없으므로 그 파서를
쓰지 않는다.

**문장 경계를 아는 쪽이 나눈다.** `fts_load` 가 `;\\n` 으로 문장을 끝내며 파일을 썼으니,
같은 규칙으로 여기서 나눈다. 추측이 들어갈 자리가 없다.

**한 요청에 한 문장만 보낸다.** 여러 문장을 한 `sql` 에 담아 보냈더니 D1 이 문장 안의
세미콜론에서 똑같이 넘어졌다 — `unrecognized token: "'현행 노동쟁의제도에서는 …"`. 글
안의 세미콜론은 경계가 아닌데 그렇게 읽은 것이다. 한 문장씩 보내면 쪼갤 일이 없다.
문장이 280개쯤이라 요청당 0.2초로 1분 안에 끝난다(한 문장에 80KB까지 담는다).
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request

API = 'https://api.cloudflare.com/client/v4'


def database_id(config='domains/ask/worker/wrangler.jsonc') -> str:
    """wrangler 설정에서 D1 id 를 읽는다. **두 벌로 적지 않는다** — 설정이 정본이다."""
    text = pathlib.Path(config).read_text(encoding='utf-8')
    m = re.search(r'"database_id"\s*:\s*"([0-9a-fA-F-]{36})"', text)
    if not m:
        raise SystemExit(f'{config} 에서 database_id 를 못 찾았다')
    return m.group(1)


def statements(paths) -> list[str]:
    """파일들을 문장 목록으로 만든다. 순서가 곧 실행 순서다(DELETE 가 맨 앞)."""
    out = []
    for p in paths:
        text = pathlib.Path(p).read_text(encoding='utf-8')
        for 문장 in text.split(';\n'):
            문장 = 문장.strip()
            if 문장:
                out.append(문장)
    return out


def post(sql: str, *, account: str, db: str, token: str, opener=None) -> dict:
    req = urllib.request.Request(
        f'{API}/accounts/{account}/d1/database/{db}/query',
        data=json.dumps({'sql': sql}).encode('utf-8'),
        headers={'authorization': f'Bearer {token}', 'content-type': 'application/json'},
        method='POST')
    열기 = opener or urllib.request.urlopen
    try:
        with 열기(req, timeout=120) as res:
            body = json.loads(res.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        # **본문을 같이 싣는다.** 상태 코드만으로는 어느 문장이 왜 거부됐는지 모른다.
        raise SystemExit(f'D1 거부 {e.code}: {e.read().decode("utf-8", "replace")[:500]}')
    if not body.get('success'):
        raise SystemExit(f'D1 실패: {json.dumps(body.get("errors"), ensure_ascii=False)[:500]}')
    return body


def main(argv=None) -> int:
    paths = list(sys.argv[1:] if argv is None else argv)
    if not paths:
        raise SystemExit('밀어 넣을 .sql 파일을 인자로 준다')
    token = os.environ.get('CLOUDFLARE_API_TOKEN')
    account = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
    if not token or not account:
        raise SystemExit('CLOUDFLARE_API_TOKEN·CLOUDFLARE_ACCOUNT_ID 가 필요하다')
    db = database_id()

    stmts = statements(sorted(paths))
    print(f'{len(stmts)} 문장을 하나씩 보낸다', file=sys.stderr)
    for i, sql in enumerate(stmts, start=1):
        post(f'{sql};', account=account, db=db, token=token)
        if i % 25 == 0 or i == len(stmts):
            print(f'  {i}/{len(stmts)}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
