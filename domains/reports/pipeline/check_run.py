"""회차 성공/실패 판정.

**실패는 게시판 단위로 둘뿐이다** — 요청 자체가 실패했거나, 목록을 200으로
받았는데 항목이 0건이거나. 뒤쪽이 마크업 변경 신호다.

**신규 글이 0건인 것은 실패가 아니다.** 고용영향평가브리프·패널브리프처럼 몇
달씩 아무것도 안 올라오는 게 정상인 게시판이 있다. 그것을 실패로 잡으면 조용한
달마다 알람이 울리고, 알람이 일상이 되면 진짜 고장을 아무도 안 본다.

`KNOWN_DOWN` 은 알람이지 스위치가 아니다. `보드id@YYYY-MM-DD` 로 적어 두면 그
게시판의 실패를 기한까지 통과시키지만, 기한이 지났거나 그 게시판이 되살아나면
일부러 실패시킨다 — 지우게 만들려는 것이다.

  python -m domains.reports.pipeline.check_run
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
DATA = Path(__file__).resolve().parent.parent / 'data'


def _parse_known_down(spec: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for chunk in (spec or '').split(','):
        chunk = chunk.strip()
        if not chunk:
            continue
        board, _, deadline = chunk.partition('@')
        out[board.strip()] = deadline.strip()
    return out


def check(last_run: dict, known_down: str = '', today: str = '') -> tuple[int, list[str]]:
    today = today or datetime.now(KST).date().isoformat()
    allowed = _parse_known_down(known_down)
    msgs: list[str] = []
    failed = False

    boards = last_run.get('boards') or {}
    for board_id, result in sorted(boards.items()):
        ok = bool(result.get('ok'))
        deadline = allowed.get(board_id)
        if not ok:
            reason = result.get('error') or '알 수 없는 실패'
            if deadline and today <= deadline:
                msgs.append(f'{board_id}: 실패했지만 KNOWN_DOWN 으로 통과 ({reason})')
                continue
            if deadline:
                msgs.append(f'{board_id}: KNOWN_DOWN 기한({deadline})이 지났다 — {reason}')
            else:
                msgs.append(f'{board_id}: {reason}')
            failed = True
        elif deadline:
            msgs.append(f'{board_id}: 되살아났다. KNOWN_DOWN 에서 지워라')
            failed = True
        elif not result.get('added'):
            msgs.append(f'{board_id}: 신규 없음 (정상)')

    for href in last_run.get('unregistered') or []:
        msgs.append(f'미등록 게시판: {href}')

    missing = last_run.get('abstract_missing') or {}
    for org, series in sorted(missing.items()):
        for name, cell in sorted(series.items()):
            if cell.get('rate', 0) >= 0.5 and cell.get('total', 0) >= 10:
                msgs.append(f'초록 결측률 높음: {org}/{name} '
                            f"{cell['missing']}/{cell['total']}")

    if not boards:
        msgs.append('수집한 게시판이 없다')
    return (1 if failed else 0), msgs


def main(argv=None) -> int:
    path = DATA / 'last_run.json'
    last = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    code, msgs = check(last, os.environ.get('KNOWN_DOWN', ''))
    for m in msgs:
        print(m)
    print('FAIL' if code else 'OK')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
