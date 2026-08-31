from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from . import store
from .collectors import bok, imf, kdi, keis, kiet, kli, oecd
from .models import ForecastRecord

KST = timezone(timedelta(hours=9))
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

COLLECTORS: dict[str, Callable[[date], list[ForecastRecord]]] = {
    "oecd": oecd.collect,
    "imf": imf.collect,
    "bok": bok.collect,
    "kdi": kdi.collect,
    "kli": kli.collect,
    "kiet": kiet.collect,
    "keis": keis.collect,
}


def main(data_dir: Path = DATA_DIR,
         collectors: dict[str, Callable[[date], list[ForecastRecord]]] = COLLECTORS,
         ) -> int:
    forecasts_path = data_dir / "forecasts.json"
    last_run_path = data_dir / "last_run.json"
    today = datetime.now(KST).date()

    existing = store.load_forecasts(forecasts_path)
    merged = existing
    summary = {
        "run_at": datetime.now(KST).isoformat(),
        "collectors": {},
        "conflicts": [],
        "errors": [],
    }

    for name, collect_fn in collectors.items():
        try:
            candidates = collect_fn(today)
            # 값이 그대로여도 버리지 않는다. published_at 이 발표일이 된 뒤로 id 가
            # 회차마다 고정돼, 값 비교로 거르면 그 회차가 통째로 사라진다.
            # 같은 회차를 다시 받은 경우는 store.merge 가 id 로 걸러낸다.
            result = store.merge(merged, candidates)
            merged = result.records
            summary["conflicts"].extend(result.conflicts)
            summary["collectors"][name] = {
                "ok": True, "fetched": len(candidates), "added": len(result.added),
            }
        except Exception as exc:
            # last_run.json 은 저장소에 커밋된다 — 트레이스백을 담으면 돌린 사람의
            # 절대경로까지 함께 실린다. 무엇이 왜 실패했는지만 한 줄로 남긴다.
            summary["collectors"][name] = {"ok": False, "fetched": 0, "added": 0}
            summary["errors"].append(f"{name}: {type(exc).__name__}: {exc}")

    if len(merged) != len(existing):
        store.save_forecasts(forecasts_path, merged)
    last_run_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary["collectors"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
