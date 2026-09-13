"""적재된 FTS 색인이 네 도메인을 다 담고 있는지 확인한다.

  npx wrangler@4 d1 execute ... --json --command "SELECT 도메인, COUNT(*) AS n FROM doc_fts GROUP BY 도메인" \
    | python -m tools.fts_verify

**왜 필요한가.** 2026-09-13 에 색인 적재가 조용히 반만 됐다. wrangler 가 큰 SQL 파일의
뒤쪽 문장을 버리며 `Warning: leftover buffer from sql.ingest` 만 남기고 **종료코드 0** 으로
끝났고, 색인에는 reports 만 남았다(forecast·press·카탈로그 526행 소실). 워크플로는 초록,
화면은 "이 질문으로 걸리는 글이 없다" — 사용자가 알 길이 없는 실패였다.

**빈 색인이 낡은 색인보다 나쁘다**는 이 워크플로의 원칙을 적재 뒤에도 한 번 더 적용한다.
"""
from __future__ import annotations

import json
import sys

# 색인이 담아야 하는 도메인. 하나라도 비면 실패다.
필수 = ('reports', 'forecast', 'press', 'catalog')


def 건수(payload) -> dict[str, int]:
    """wrangler --json 출력에서 도메인별 건수를 뽑는다.

    출력은 `[{"results": [...], "success": true, ...}]` 꼴이다. 형태가 바뀌면
    조용히 0건으로 읽지 말고 터뜨린다 — 확인기가 확인을 못 하는 것이 가장 나쁘다.
    """
    데이터 = json.loads(payload) if isinstance(payload, str) else payload
    if isinstance(데이터, dict):
        데이터 = [데이터]
    rows = []
    for 덩이 in 데이터:
        rows.extend(덩이.get('results') or [])
    if not rows:
        raise SystemExit('확인 실패: 조회 결과가 비어 있다 — 적재가 통째로 안 됐거나 출력 형식이 바뀌었다')
    return {str(r['도메인']): int(r['n']) for r in rows}


def main(argv=None) -> int:
    있음 = 건수(sys.stdin.read())
    for d in sorted(있음):
        print(f'{d}\t{있음[d]}')
    빈것 = [d for d in 필수 if not 있음.get(d)]
    if 빈것:
        print(f'적재가 반만 됐다 — 비어 있는 도메인: {", ".join(빈것)}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
