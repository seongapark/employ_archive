"""수집 결과를 보고 그날 실행을 실패로 볼지 판정한다(워크플로 마지막 스텝).

수집기 하나가 오래 죽어 있으면 매일 빨개져서, 정작 다른 수집기가 깨진 날을
알아채지 못한다. 원인을 이미 아는 장애는 KNOWN_DOWN 에 적어 로그로만 남긴다.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def known_down_from_env() -> set[str]:
    return {n.strip() for n in os.environ.get("KNOWN_DOWN", "").split(",") if n.strip()}


def main(last_run_path: Path = DATA_DIR / "last_run.json", *,
         known_down: set[str] | None = None) -> int:
    known = known_down_from_env() if known_down is None else known_down
    run = json.loads(Path(last_run_path).read_text(encoding="utf-8"))

    unexpected = []
    for error in run["errors"]:
        name = error.split(":", 1)[0].strip()
        if name in known:
            print(f"::notice::알고 있는 장애라 넘어간다 — {error}")
        else:
            unexpected.append(error)
            print(f"::error::{error}")

    for name in sorted(known):
        if run["collectors"].get(name, {}).get("ok"):
            print(f"::warning::{name} 가 다시 수집됐다 — 워크플로의 KNOWN_DOWN 에서 지울 것")

    return 1 if unexpected else 0


if __name__ == "__main__":
    # 워크플로는 UTF-8 이지만 로컬 콘솔은 아닐 수 있다(윈도우 cp949).
    # 판정 결과를 쓰다 터지면 멀쩡한 실행이 실패로 둔갑한다.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
