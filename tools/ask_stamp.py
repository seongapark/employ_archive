# -*- coding: utf-8 -*-
"""FTS 색인 적재 결과를 질의응답 도메인의 현황으로 남긴다.

  python -m tools.ask_stamp /tmp/fts/counts.json --status success

**왜 있나.** `domains/ask/data/last_run.json` 은 2026-09-08 에 손으로 한 번 쓰이고
아무도 다시 쓰지 않았다. 관리자 화면은 그 파일을 읽어 "카탈로그 정상 · 137시간째
안 돌았다" 를 보여줬는데, 둘 다 박아 둔 값이었다 — 카탈로그가 진짜로 깨져도 화면은
계속 '정상' 이라고 말한다. 다른 네 도메인은 워크플로가 매번 다시 쓴다.

**왜 sync-catalog 가 아니라 sync-fts 인가.** sync-catalog 는 ask 설정 파일이 바뀔
때만 돈다 — 평소엔 몇 주씩 낡아 보인다. sync-fts 는 네 도메인 데이터가 바뀔 때마다
(사실상 매일) 돌고, 카탈로그 행까지 같은 색인에 싣는다. 그래서 이 카드는 "어제
색인이 성공적으로 실렸다" 를 뜻한다.

**실패도 기록한다.** 적재가 깨진 날 기록을 아예 안 남기면 화면은 '오래됐다' 라고만
하고 무엇이 틀렸는지는 말하지 못한다.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
OUT = Path(__file__).resolve().parent.parent / 'domains' / 'ask' / 'data' / 'last_run.json'

# fts_verify 와 같은 목록이다. 하나라도 비면 색인이 반만 실린 것이다.
필수 = ('reports', 'forecast', 'press', 'catalog')


def 기록(counts: dict, *, ok: bool, now: datetime | None = None) -> dict:
    """관리자 화면(어댑터_ask)이 읽는 모양으로 만든다.

    `run_at` 과 `catalog.ok` 는 그 어댑터가 요구하는 필드다 — 이름을 바꾸면
    카드가 통째로 '형식오류' 가 된다. 나머지는 사람이 읽을 덤이다.
    """
    셈 = {str(k): int(v) for k, v in (counts or {}).items()}
    빈도메인 = [d for d in 필수 if 셈.get(d, 0) <= 0]
    성공 = bool(ok) and not 빈도메인
    out = {
        'run_at': (now or datetime.now(KST)).isoformat(timespec='seconds'),
        'catalog': {'ok': 성공, 'rows': 셈.get('catalog', 0)},
        'fts': {'rows': sum(셈.values()), '도메인': dict(sorted(셈.items()))},
    }
    if 빈도메인:
        out['catalog']['빈도메인'] = 빈도메인
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('counts', nargs='?', help='fts_load 가 남긴 counts.json')
    ap.add_argument('--status', default='success',
                    help="앞 단계 결과(success 면 성공). 실패한 회차도 기록한다")
    ap.add_argument('--out', default=str(OUT))
    args = ap.parse_args(argv)

    counts = {}
    if args.counts:
        p = Path(args.counts)
        # 적재기가 먼저 죽으면 이 파일이 없다. 그 경우도 기록은 남긴다 —
        # 0건으로 남겨야 화면이 '실패' 라고 말할 수 있다.
        if p.exists():
            counts = json.loads(p.read_text(encoding='utf-8'))

    데이터 = 기록(counts, ok=(args.status == 'success'))
    Path(args.out).write_text(json.dumps(데이터, ensure_ascii=False, indent=1) + '\n',
                              encoding='utf-8')
    print(f"질의응답 현황 기록: ok={데이터['catalog']['ok']} "
          f"색인 {데이터['fts']['rows']}행 ({데이터['run_at']})")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
