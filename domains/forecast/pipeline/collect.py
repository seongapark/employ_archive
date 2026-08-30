from __future__ import annotations

import json
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from . import store
from .collectors import bok, imf, kdi, oecd
from .models import ForecastRecord

KST = timezone(timedelta(hours=9))
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

COLLECTORS: dict[str, Callable[[date], list[ForecastRecord]]] = {
    "oecd": oecd.collect,
    "imf": imf.collect,
    "bok": bok.collect,
    "kdi": kdi.collect,
}


def drop_unchanged(existing: list[ForecastRecord],
                   candidates: list[ForecastRecord]) -> list[ForecastRecord]:
    fresh = []
    for cand in candidates:
        latest = store.latest_record(
            existing, cand.org, cand.indicator, cand.target_year, cand.target_period
        )
        if latest is not None and latest.value == cand.value:
            continue
        fresh.append(cand)
    return fresh


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
            fresh = drop_unchanged(merged, candidates)
            result = store.merge(merged, fresh)
            merged = result.records
            summary["conflicts"].extend(result.conflicts)
            summary["collectors"][name] = {
                "ok": True, "fetched": len(candidates), "added": len(result.added),
            }
        except Exception:
            summary["collectors"][name] = {"ok": False, "fetched": 0, "added": 0}
            summary["errors"].append(f"{name}: {traceback.format_exc(limit=3)}")

    if len(merged) != len(existing):
        store.save_forecasts(forecasts_path, merged)
    last_run_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary["collectors"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
