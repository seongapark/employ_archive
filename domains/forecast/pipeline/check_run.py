"""수집 결과를 보고 그날 실행을 실패로 볼지 판정한다(워크플로 마지막 스텝).

수집기 하나가 오래 죽어 있으면 매일 빨개져서, 정작 다른 수집기가 깨진 날을
알아채지 못한다. 원인을 이미 아는 장애는 KNOWN_DOWN 에 적어 로그로만 남긴다.

유예에는 기한을 반드시 붙인다(`kdi@2026-09-30`). 기한 없는 유예는 그대로
굳어서, 나중에 그 수집기가 조용히 빠져도 아무도 모르게 된다. 그래서
 - 기한이 지나면 다시 실패시킨다. 장애가 안 끝났으면 기한만 미루면 된다.
 - 적어둔 수집기가 되살아나면 실패시킨다. 초록 실행에 붙은 경고는 아무도
   보지 않으므로, 목록에서 지울 때까지 빨갛게 둔다.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def parse_known_down(text: str) -> dict[str, date]:
    """`kdi@2026-09-30, bok@2026-12-01` 을 {수집기: 유예 만료일} 로 읽는다."""
    entries: dict[str, date] = {}
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, sep, deadline = chunk.partition("@")
        if not sep:
            raise ValueError(f"KNOWN_DOWN 항목에 기한이 없다: {chunk!r} — 'kdi@2026-09-30' 형태로 적는다")
        try:
            entries[name.strip()] = datetime.strptime(deadline.strip(), "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(f"KNOWN_DOWN 기한을 읽을 수 없다: {chunk!r} — YYYY-MM-DD 로 적는다") from None
    return entries


def main(last_run_path: Path = DATA_DIR / "last_run.json", *,
         known_down: dict[str, date] | None = None,
         today: date | None = None) -> int:
    if today is None:
        today = datetime.now(KST).date()
    if known_down is None:
        try:
            known_down = parse_known_down(os.environ.get("KNOWN_DOWN", ""))
        except ValueError as exc:
            print(f"::error::{exc}")
            return 1

    run = json.loads(Path(last_run_path).read_text(encoding="utf-8"))
    failed = False

    for error in run["errors"]:
        name = error.split(":", 1)[0].strip()
        deadline = known_down.get(name)
        if deadline is None:
            failed = True
            print(f"::error::{error}")
        elif today > deadline:
            failed = True
            print(f"::error::{name} 유예가 {deadline} 로 끝났다 — 아직 못 고쳤으면 "
                  f"KNOWN_DOWN 의 기한을 미루고, 고칠 수 있으면 고친다. {error}")
        else:
            print(f"::notice::알고 있는 장애라 {deadline} 까지 넘어간다 — {error}")

    for name, deadline in sorted(known_down.items()):
        if run["collectors"].get(name, {}).get("ok"):
            failed = True
            print(f"::error::{name} 가 다시 수집됐다 — 워크플로의 KNOWN_DOWN 에서 "
                  f"'{name}@{deadline}' 를 지울 것. 남겨두면 다음에 조용히 빠져도 모른다")

    return 1 if failed else 0


if __name__ == "__main__":
    # 워크플로는 UTF-8 이지만 로컬 콘솔은 아닐 수 있다(윈도우 cp949).
    # 판정 결과를 쓰다 터지면 멀쩡한 실행이 실패로 둔갑한다.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_DIR / "last_run.json"
    raise SystemExit(main(path))
