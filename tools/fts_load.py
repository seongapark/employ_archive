"""초록·목차·전망근거·카탈로그 설명을 D1 의 FTS 색인(`doc_fts`)으로 옮긴다.

  python -m tools.fts_load > /tmp/fts.sql

`tools/d1_sync.py` 와 같은 방식이다 — **실행하지 않고 SQL 만 표준출력으로 낸다.**
워크플로가 `wrangler d1 execute --file` 로 밀어넣는다. 그래야 테스트가 네트워크에
안 나가고, D1 이 죽어도 수집이 죽지 않는다.

담는 것은 넷이다. 전부 이미 저장소에 있으면서 **검색 대상이 아니었던** 글이다.

  reports  초록·목차     domains/reports/data/abstracts.json + reports.json
  forecast 전망근거      domains/forecast/data/rationales.json
  press    기사·회차분석  domains/press/data/articles.json · rounds.json
  catalog  충돌·한계     domains/ask/data/conflicts.json · capabilities.json

원문 PDF 본문은 담지 않는다(450건·약 39,000쪽 → 색인 포함 0.5~1GB 로 무료 플랜
500MB 를 넘는다). 필요해지면 그때 다시 잰다.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

from .d1_sync import REPO, sql_literal

COLUMNS = ['doc_id', '도메인', '종류', '링크', '제목', '본문', '날짜', '제목색인', '본문색인']

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
#
# D1 한도(100KB)보다 한참 낮게 잡은 이유는 **wrangler 쪽**이다. 2026-09-13 에 한 파일로
# 5,379행을 밀었더니 `Warning: leftover buffer from sql.ingest` 를 내며 뒤쪽 문장들을
# 조용히 버리고 **종료코드 0** 으로 끝났다 — 색인에 reports 만 남고 forecast·press·
# 카탈로그 526행이 사라졌는데 워크플로는 초록이었다. 문장을 작게 끊고(아래) 도메인별
# 파일로 나눠 밀고(`write_files`) 적재 뒤 도메인별 건수를 확인하는(`verify.py`) 세 겹으로
# 막는다.
BUDGET = 80_000

_WS = re.compile(r'\s+')
# 문장 끝. 한국어 종결어미와 마침표를 함께 본다 — 초록에는 마침표 없이 끝나는
# 개조식 문장이 흔하다.
_SENT = re.compile(r'(?<=[.?!])\s+|(?<=다\.)\s*|(?<=음\.)\s*|(?<=함\.)\s*')


# 게시판에서 긁어 온 초록에는 **본문이 아닌 것**이 섞여 있다 — CSS 규칙 블록,
# JSON-LD, HTML 태그, 엔티티. 그대로 색인하면 두 가지가 망가진다.
#
# ① 검색 품질: 스니펫에 `color:#ffffff;` 가 뜨고, 색인이 CSS 낱말로 찬다.
# ② **적재가 조용히 반만 된다.** CSS 는 `;` 뒤에 줄바꿈이 오는데, 그 `;\n` 이 SQL 문자열
#    안에 들어가면 wrangler 의 원격 ingest 가 문장이 끝난 줄로 읽는다 — 2026-09-13 에
#    `leftover buffer from sql.ingest` 경고와 함께 115행이 사라졌고 종료코드는 0이었다
#    (CSS 블록이 든 두 파일에서만 났다. 인용문의 `; ` 는 줄바꿈이 아니라 멀쩡했다).
#    그래서 여기서 **모든 공백을 한 칸으로 접는다** — 값 안에 줄바꿈이 남지 않는다.
#
# 뿌리는 수집기다(기관 페이지의 style 블록까지 초록으로 담았다). 다만 색인으로 들어오는
# 글이 전부 이 함수를 지나므로, 한 곳에서 막는 것이 재수집보다 싸고 확실하다.
# SQL 주석으로 읽히는 글자 짝. **이것이 적재를 반만 되게 한 두 번째 원인이다** —
# 게시판 CSS 에 `/* 표 헤더 스타일 */` 같은 주석이 남아 있고 보도자료 상투구에 `//*` 가
# 있어서, 생성된 SQL 전체에 `/*` 가 207개인데 `*/` 는 54개였다. 짝이 안 맞으니 원격
# ingest 가 파일 끝까지 주석으로 삼켜 뒤쪽 INSERT 를 통째로 버렸다(종료코드는 0).
# 주석 표시는 색인할 글에서 아무 뜻이 없으므로 짝을 지어 지우고 남은 조각도 지운다.
_COMMENT = re.compile(r'/\*.*?\*/', re.S)
_COMMENT_MARK = re.compile(r'/\*|\*/|--+')
_TAGBLOCK = re.compile(r'(?is)<(style|script)[^>]*>.*?</\1>')
_TAG = re.compile(r'<[^<>]{0,400}>')
_BRACE = re.compile(r'\{[^{}]{0,4000}\}')
_ENTITY = re.compile(r'&[a-zA-Z]{2,8};|&#\d{2,5};')
_ENTITIES = {'&nbsp;': ' ', '&amp;': '&', '&lt;': '<', '&gt;': '>',
             '&quot;': '"', '&#39;': "'", '&apos;': "'"}


def plain(text) -> str:
    """본문에서 마크업·CSS·JSON 블록을 걷어내고 공백을 한 칸으로 접는다."""
    s = str(text or '')
    s = _COMMENT.sub(' ', s)
    s = _TAGBLOCK.sub(' ', s)
    s = _TAG.sub(' ', s)
    # 중괄호 블록이 CSS·JSON 이면 통째로 버린다. 글에 쓰인 중괄호는 `:`·`;` 가 없어 남는다.
    for _ in range(4):
        나중 = _BRACE.sub(lambda m: ' ' if (':' in m.group(0) or ';' in m.group(0)) else m.group(0), s)
        if 나중 == s:
            break
        s = 나중
    for k, v in _ENTITIES.items():
        s = s.replace(k, v)
    s = _ENTITY.sub(' ', s)
    # 짝이 없어 남은 주석 표시. 여기까지 오면 글이 아니라 마크업 잔해다.
    s = _COMMENT_MARK.sub(' ', s)
    return _WS.sub(' ', s).strip()


def squash(s) -> str:
    """공백을 전부 지운다.

    trigram 은 공백까지 그대로 맞아야 걸린다(2026-09-10 실물 D1 실측) — 본문이
    "청년고용" 이면 `청년 고용` 이 0건이다. 색인 사본과 질의 양쪽에서 같은 규칙으로
    지워야 그 문제가 사라진다. 웹앱 검색의 `squash()` 와 같은 해법이다.

    **공백을 지우면 주석 표시가 새로 생긴다.** 보도자료 상투구 `.// *세부내용은` 이
    공백을 잃으면 `.//*세부내용은` 이 되어 `/*` 가 만들어진다 — 원문에는 없던 짝이다.
    그래서 지운 뒤 한 번 더 걷어낸다(왜 위험한지는 `_COMMENT_MARK` 주석).
    """
    return _COMMENT_MARK.sub('', _WS.sub('', str(s or '')))


def chunks(text: str, limit: int = CHUNK) -> list[str]:
    """문장 경계에서 자른다. 문장 하나가 상한을 넘으면 그 문장을 통으로 자른다.

    문단 경계로 자르고 싶어도 못 자른다 — PDF 에서 뽑은 초록은 공백을 합쳐 넣었고
    게시판에서 받은 초록도 줄바꿈 보존 이전 파싱이라 문단이 없다.
    """
    s = plain(text)
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


def _row(doc_id, 도메인, 종류, 링크, 제목, 본문, 날짜='') -> dict:
    """한 행. `날짜` 는 정렬·필터용이고 검색어가 아니다(0005 주석 참조).

    `YYYY-MM-DD` 나 `YYYY-MM` 만 담는다 — 문자열 비교로 기간을 거르므로 자리수가
    어긋나면 조용히 틀린다. 값이 없으면 **빈 문자열**이고, 카탈로그의 한계·충돌이
    거기 해당한다(상시 사실이라 날짜가 없다).
    """
    제목 = plain(제목)
    본문 = plain(본문)
    return {
        'doc_id': doc_id, '도메인': 도메인, '종류': 종류,
        '링크': 링크 or '', '제목': 제목, '본문': 본문, '날짜': 날짜 or '',
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
        날짜 = m.get('published') or ''
        for i, c in enumerate(chunks(b.get('abstract') or '')):
            out.append(_row(f'reports:{rid}:초록:{i}', 'reports', '초록', 링크, 제목, c, 날짜))
        # 초록이 없는 보고서가 257건이다. 목차라도 걸려야 그 보고서가 검색에 존재한다.
        toc = ' / '.join(b.get('toc') or [])
        for i, c in enumerate(chunks(toc)):
            out.append(_row(f'reports:{rid}:목차:{i}', 'reports', '목차', 링크, 제목, c, 날짜))
    return out


def _forecast() -> list[dict]:
    out = []
    for r in _load('domains/forecast/data/rationales.json'):
        제목 = f"{r.get('org', '')} {r.get('published_at', '')} {r.get('indicator', '')}".strip()
        key = f"forecast:{r.get('org')}:{r.get('published_at')}:{r.get('indicator')}"
        for i, c in enumerate(chunks(r.get('text') or '')):
            out.append(_row(f'{key}:{i}', 'forecast', '전망근거',
                            r.get('source_url') or '', 제목, c,
                            r.get('published_at') or ''))
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


def _press() -> list[dict]:
    """기사 제목과 회차 분석.

    **기사 본문은 없다** — press 도메인이 저장하지 않는다(제목·언론사·인용여부·
    논조 낱말뿐). 그래서 제목이 곧 본문이고, 링크가 생명이다. 기사가 뭐라고
    했는지는 가서 읽어야 한다.
    """
    arts = _load('domains/press/data/articles.json')
    out = []
    for release, 묶음 in arts.items():
        for 구분 in ('regular', 'follow'):
            for i, a in enumerate(묶음.get(구분) or []):
                제목 = f"{release} {a.get('press', '')} {'정규' if 구분 == 'regular' else '후속'}"
                본문 = a.get('title') or ''
                if not 본문:
                    continue
                out.append(_row(f'press:{release}:{구분}:{i}', 'press', '기사',
                                a.get('url') or '', 제목, 본문, release))

    # 회차 분석은 "우리 발표가 어떻게 받아졌나" 를 묻는 질문의 답이다. 누락·논조·
    # 쟁점을 한 행에 모은다 — 따로 두면 "왜" 를 물었을 때 조각만 걸린다.
    for r in _load('domains/press/data/rounds.json'):
        제목 = f"{r.get('label', '')} {r.get('title', '')}".strip() or str(r.get('release'))
        조각 = []
        for g in r.get('gaps') or []:
            조각.append(str(g))
        논조 = ' · '.join(f"{x.get('w')} {x.get('n')}건" for x in (r.get('tone') or []))
        if 논조:
            조각.append(f'자주 쓰인 낱말: {논조}')
        for x in r.get('issues') or []:
            heads = ' / '.join(h.get('title', '') for h in (x.get('heads') or [])[:3])
            조각.append(f"쟁점 {x.get('key')} {x.get('n')}건 — {heads}")
        본문 = ' '.join(조각)
        for i, c in enumerate(chunks(본문)):
            out.append(_row(f"press:{r.get('release')}:회차:{i}", 'press', '회차분석',
                            '', 제목, c, str(r.get('release') or '')))
    return out


def rows() -> list[dict]:
    return [*_reports(), *_forecast(), *_press(), *_catalog()]


def build_sql(rs: list[dict], batch: int = BATCH, budget: int = BUDGET,
              지우기: bool = True) -> str:
    """비우고 다시 넣는다.

    FTS5 가상표는 `ON CONFLICT` 를 못 받아 `d1_sync` 의 upsert 방식을 쓸 수 없다.
    전량 재적재라 중간에 끊겨도 다시 돌리면 같은 상태가 된다.

    `지우기=False` 는 도메인별 파일을 쓸 때다 — DELETE 를 파일마다 넣으면 뒤 파일이
    앞 파일이 넣은 것을 지운다.
    """
    out = ['DELETE FROM doc_fts;'] if 지우기 else []
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


def write_files(out_dir) -> list[tuple[str, int]]:
    """도메인별 SQL 파일을 쓴다. 앞 번호가 실행 순서다.

    **한 파일로 밀지 않는다.** wrangler 의 `--file` 이 큰 파일의 뒤쪽을 조용히 버린
    적이 있다(위 BUDGET 주석). 나눠 두면 한 파일이 통째로 실패해도 어느 도메인이
    비었는지 곧 드러나고, 적재 뒤 건수 확인이 그 사실을 잡는다.

    `00_delete.sql` 만 표를 비운다 — 도메인 파일은 INSERT 뿐이라 순서를 바꿔도 안전하다.
    """
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / '00_delete.sql').write_text('DELETE FROM doc_fts;\n', encoding='utf-8')
    지은것 = [('00_delete.sql', 0)]
    for i, (도메인, 만들기) in enumerate(
            [('reports', _reports), ('forecast', _forecast),
             ('press', _press), ('catalog', _catalog)], start=1):
        rs = 만들기()
        # 파일도 크면 안 된다 — reports 한 도메인이 19MB 라 한 파일로 두면 같은 곳에서
        # 또 뒤가 잘린다. 도메인 안에서도 조각으로 나눈다.
        for j, 조각 in enumerate(_파일조각(rs), start=1):
            name = f'{i * 10:02d}_{도메인}_{j:02d}.sql'
            (out_dir / name).write_text(build_sql(조각, 지우기=False), encoding='utf-8')
            지은것.append((name, len(조각)))
    # **예상 건수를 남긴다.** 도메인이 비었는지만 보면 4% 가 사라진 적재를 통과시킨다
    # (실측). 확인기가 이 숫자와 실제 건수를 맞춰 본다.
    셈: dict[str, int] = {}
    for name, n in 지은것:
        if name == '00_delete.sql':
            continue
        셈[name.split('_')[1]] = 셈.get(name.split('_')[1], 0) + n
    (out_dir / 'counts.json').write_text(json.dumps(셈, ensure_ascii=False), encoding='utf-8')
    return 지은것


# 한 파일의 바이트 상한.
#
# **작게 유지한다.** wrangler 의 원격 ingest 는 파일을 일정 크기로 나눠 읽으면서 경계에
# 걸친 문장을 버린다 — `leftover buffer from sql.ingest` 경고를 남기고 종료코드 0 으로
# 끝난다. 2MB 에서 202행, 700KB 에서 138행이 그렇게 사라졌다(실측). 내용을 정리해도
# (CSS·주석·줄바꿈) 같은 자리에서 같은 수가 사라져, 원인은 글이 아니라 **바이트 경계**로
# 보인다. 경계가 아예 안 생기도록 조각을 더 줄인다. 조각당 0.3초라 값이 싸다.
FILE_BUDGET = 400_000


def _파일조각(rs: list[dict], budget: int = FILE_BUDGET):
    조각: list[dict] = []
    size = 0
    for r in rs:
        n = sum(len(str(r.get(c) or '').encode('utf-8')) for c in COLUMNS) + 40
        if 조각 and size + n > budget:
            yield 조각
            조각, size = [], 0
        조각.append(r)
        size += n
    if 조각:
        yield 조각


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == '--out-dir':
        for name, n in write_files(argv[1]):
            print(f'{name}\t{n}', file=sys.stderr)
        return 0
    rs = rows()
    sys.stdout.write(build_sql(rs))
    print(f'-- {len(rs)} rows', file=sys.stderr)
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
