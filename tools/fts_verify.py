"""적재된 FTS 색인이 만든 것과 같은지 확인한다.

  npx wrangler@4 d1 execute ... --json \
    --command "SELECT 도메인, COUNT(*) AS n FROM doc_fts GROUP BY 도메인" \
    | python -m tools.fts_verify /tmp/fts/counts.json

**왜 필요한가.** 2026-09-13 에 색인 적재가 두 번 조용히 반만 됐다. wrangler 가 큰 SQL
파일의 문장을 버리며 `Warning: leftover buffer from sql.ingest` 만 남기고 **종료코드 0**
으로 끝났다 — 처음에는 reports 만 남아 526행이 사라졌고(다른 세 도메인 전멸), 파일을
나눈 뒤에도 조각 경계에서 202행이 사라졌다. 워크플로는 두 번 다 초록이었고 화면은
"이 질문으로 걸리는 글이 없다" 를 냈다.

**도메인이 비었는지만 보면 두 번째 실패를 통과시킨다.** 그래서 적재기가 남긴 예상
건수(`counts.json`)와 실제 건수를 도메인별로 맞춰 본다. 인자를 안 주면 "비지 않았는가"
만 본다 — 손으로 확인할 때의 최소 검사다.
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


def 어긋난것(실제: dict[str, int], 예상: dict[str, int] | None) -> list[str]:
    """무엇이 잘못됐는지 사람이 읽을 줄로 낸다. 빈 목록이면 통과다."""
    말 = []
    for d in 필수:
        if not 실제.get(d):
            말.append(f'{d}: 비었다')
    for d, n in sorted((예상 or {}).items()):
        있는것 = 실제.get(d, 0)
        if 있는것 != n:
            말.append(f'{d}: {n}행을 만들었는데 {있는것}행만 들어갔다')
    return 말


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    예상 = None
    if argv:
        예상 = json.loads(open(argv[0], encoding='utf-8').read())
    실제 = 건수(sys.stdin.read())
    for d in sorted(실제):
        print(f'{d}\t{실제[d]}')
    문제 = 어긋난것(실제, 예상)
    if 문제:
        print('적재가 어긋났다:', file=sys.stderr)
        for x in 문제:
            print(f'  - {x}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
