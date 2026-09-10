"""초록·목차·전망근거·카탈로그 설명을 D1 의 FTS 색인(`doc_fts`)으로 옮긴다.

  python -m tools.fts_load > /tmp/fts.sql

`tools/d1_sync.py` 와 같은 방식이다 — **실행하지 않고 SQL 만 표준출력으로 낸다.**
워크플로가 `wrangler d1 execute --file` 로 밀어넣는다. 그래야 테스트가 네트워크에
안 나가고, D1 이 죽어도 수집이 죽지 않는다.

담는 것은 넷이다. 전부 이미 저장소에 있으면서 **검색 대상이 아니었던** 글이다.

  reports  초록·목차     domains/reports/data/abstracts.json + reports.json
  forecast 전망근거      domains/forecast/data/rationales.json
  catalog  충돌·한계     domains/ask/data/conflicts.json · capabilities.json

원문 PDF 본문은 담지 않는다(450건·약 39,000쪽 → 색인 포함 0.5~1GB 로 무료 플랜
500MB 를 넘는다). 필요해지면 그때 다시 잰다.
"""
from __future__ import annotations

import json
import re
import sys

from .d1_sync import REPO, sql_literal

COLUMNS = ['doc_id', '도메인', '종류', '링크', '제목', '본문', '제목색인', '본문색인']

# 한 행의 본문 상한. 스니펫으로 보여줄 수 있는 크기여야 한다 — 초록 한 건이
# 6천 자라 통째로 넣으면 어디가 걸렸는지 보여줄 수가 없다.
CHUNK = 2000
# 한 INSERT 에 묶는 행 수의 **상한**. 실제로 끊는 기준은 아래 BUDGET(바이트)다.
BATCH = 200
# 한 문장의 바이트 예산. D1 은 한 문장이 100KB 를 넘으면 거부한다.
#
# **행 수로만 끊으면 안 된다.** 한글은 UTF-8 로 한 자가 3바이트라 2000자 본문을
# 원문·색인 두 벌로 담으면 한 행이 12KB 다 — 200행이면 2.4MB 로 제한의 24배다.
# 처음에 행 수로만 끊었다가 테스트가 잡았다.
BUDGET = 80_000

_WS = re.compile(r'\s+')
# 문장 끝. 한국어 종결어미와 마침표를 함께 본다 — 초록에는 마침표 없이 끝나는
# 개조식 문장이 흔하다.
_SENT = re.compile(r'(?<=[.?!])\s+|(?<=다\.)\s*|(?<=음\.)\s*|(?<=함\.)\s*')


def squash(s) -> str:
    """공백을 전부 지운다.

    trigram 은 공백까지 그대로 맞아야 걸린다(2026-09-10 실물 D1 실측) — 본문이
    "청년고용" 이면 `청년 고용` 이 0건이다. 색인 사본과 질의 양쪽에서 같은 규칙으로
    지워야 그 문제가 사라진다. 웹앱 검색의 `squash()` 와 같은 해법이다.
    """
    return _WS.sub('', str(s or ''))


def chunks(text: str, limit: int = CHUNK) -> list[str]:
    """문장 경계에서 자른다. 문장 하나가 상한을 넘으면 그 문장을 통으로 자른다.

    문단 경계로 자르고 싶어도 못 자른다 — PDF 에서 뽑은 초록은 공백을 합쳐 넣었고
    게시판에서 받은 초록도 줄바꿈 보존 이전 파싱이라 문단이 없다.
    """
    s = str(text or '').strip()
    if not s:
        return []
    out: list[str] = []
    cur = ''
    for part in _SENT.split(s):
        part = (part or '').strip()
        if not part:
            continue
        while len(part) > limit:                 # 부호 없는 긴 글은 통으로 자른다
            if cur:
                out.append(cur.strip())
                cur = ''
            out.append(part[:limit])
            part = part[limit:]
        if len(cur) + len(part) + 1 > limit:
            if cur:
                out.append(cur.strip())
            cur = part
        else:
            cur = f'{cur} {part}'.strip() if cur else part
    if cur.strip():
        out.append(cur.strip())
    return out


def _load(rel: str):
    return json.loads((REPO / rel).read_text(encoding='utf-8'))


def _row(doc_id, 도메인, 종류, 링크, 제목, 본문) -> dict:
    return {
        'doc_id': doc_id, '도메인': 도메인, '종류': 종류,
        '링크': 링크 or '', '제목': 제목 or '', '본문': 본문,
        '제목색인': squash(제목), '본문색인': squash(본문),
    }


def _reports() -> list[dict]:
    meta = {r['id']: r for r in _load('domains/reports/data/reports.json')}
    body = _load('domains/reports/data/abstracts.json')
    out = []
    for rid, b in body.items():
        m = meta.get(rid, {})
        제목 = m.get('title') or rid
        # **원문이 아니라 기관 페이지로 보낸다.** 기관이 개정판을 올리면 링크 쪽이
        # 자동으로 최신이 된다 — reports 도메인이 상세 화면에서 쓰는 규칙과 같다.
        링크 = m.get('landing_url') or m.get('file_url') or ''
        for i, c in enumerate(chunks(b.get('abstract') or '')):
            out.append(_row(f'reports:{rid}:초록:{i}', 'reports', '초록', 링크, 제목, c))
        # 초록이 없는 보고서가 257건이다. 목차라도 걸려야 그 보고서가 검색에 존재한다.
        toc = ' / '.join(b.get('toc') or [])
        for i, c in enumerate(chunks(toc)):
            out.append(_row(f'reports:{rid}:목차:{i}', 'reports', '목차', 링크, 제목, c))
    return out


def _forecast() -> list[dict]:
    out = []
    for r in _load('domains/forecast/data/rationales.json'):
        제목 = f"{r.get('org', '')} {r.get('published_at', '')} {r.get('indicator', '')}".strip()
        key = f"forecast:{r.get('org')}:{r.get('published_at')}:{r.get('indicator')}"
        for i, c in enumerate(chunks(r.get('text') or '')):
            out.append(_row(f'{key}:{i}', 'forecast', '전망근거',
                            r.get('source_url') or '', 제목, c))
    return out


def _catalog() -> list[dict]:
    names = {s['id']: s.get('name_ko', s['id'])
             for s in _load('domains/ask/data/sources.json')}
    out = []
    for c in _load('domains/ask/data/conflicts.json'):
        제목 = f"{names.get(c.get('source_a'), c.get('source_a'))} ↔ " \
               f"{names.get(c.get('source_b'), c.get('source_b'))} · {c.get('차이유형', '')}"
        for i, part in enumerate(chunks(c.get('설명') or '')):
            out.append(_row(f"catalog:충돌:{c['id']}:{i}", 'catalog', '충돌', '', 제목, part))
    for l in _load('domains/ask/data/capabilities.json')['limits']:
        제목 = f"{names.get(l.get('source_id'), l.get('source_id'))} · {l.get('유형', '')}"
        # 내용과 사유를 한 행에 둔다. 따로 두면 "왜" 를 물었을 때 사유만 걸려
        # 무엇에 대한 사유인지 모르는 조각이 나온다.
        본문 = ' — '.join(x for x in [l.get('내용'), l.get('사유')] if x)
        for i, part in enumerate(chunks(본문)):
            out.append(_row(f"catalog:한계:{l['id']}:{i}", 'catalog', '한계', '', 제목, part))
    return out


def rows() -> list[dict]:
    return [*_reports(), *_forecast(), *_catalog()]


def build_sql(rs: list[dict], batch: int = BATCH, budget: int = BUDGET) -> str:
    """비우고 다시 넣는다.

    FTS5 가상표는 `ON CONFLICT` 를 못 받아 `d1_sync` 의 upsert 방식을 쓸 수 없다.
    전량 재적재라 중간에 끊겨도 다시 돌리면 같은 상태가 된다.
    """
    out = ['DELETE FROM doc_fts;']
    cols = ', '.join(COLUMNS)
    head = f'INSERT INTO doc_fts ({cols}) VALUES\n  '

    def flush(vals):
        if vals:
            out.append(head + ',\n  '.join(vals) + ';')

    vals, size = [], 0
    for r in rs:
        v = '(' + ', '.join(sql_literal(r.get(c)) for c in COLUMNS) + ')'
        n = len(v.encode('utf-8')) + 4
        # 바이트 예산이 먼저다. 행 수 상한은 그 위의 보조 장치일 뿐이다.
        if vals and (size + n > budget or len(vals) >= batch):
            flush(vals)
            vals, size = [], 0
        vals.append(v)
        size += n
    flush(vals)
    return '\n'.join(out) + '\n'


def main(argv=None) -> int:
    rs = rows()
    sys.stdout.write(build_sql(rs))
    print(f'-- {len(rs)} rows', file=sys.stderr)
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
