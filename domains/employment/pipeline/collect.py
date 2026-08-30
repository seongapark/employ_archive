"""고용동향 수집 오케스트레이터.

수집기 하나가 실패해도 나머지는 진행한다. 실패는 last_run.json 에 한 줄로
남긴다 — 이 파일은 저장소에 커밋되므로 트레이스백을 담으면 돌린 사람의
절대경로까지 함께 실린다.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from . import store
from .collectors import eaps, ei, est
from .models import SeriesRecord

KST = timezone(timedelta(hours=9))
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

COLLECTORS: dict[str, Callable[[date], list[SeriesRecord]]] = {
    "eaps": eaps.collect,
    "est": est.collect,
    "ei": ei.collect,
}


def load_manual(data_dir: Path) -> list[SeriesRecord]:
    """수기 입력 폴백. 파싱이 깨진 달을 손으로 채울 수 있게 한다."""
    manual_dir = data_dir / "manual"
    if not manual_dir.is_dir():
        return []
    records: list[SeriesRecord] = []
    for path in sorted(manual_dir.glob("*.json")):
        rows = json.loads(path.read_text(encoding="utf-8"))
        records.extend(SeriesRecord.model_validate(row) for row in rows)
    return records


def main(data_dir: Path = DATA_DIR,
         collectors: dict[str, Callable[[date], list[SeriesRecord]]] | None = None,
         ) -> int:
    collectors = COLLECTORS if collectors is None else collectors
    series_path = data_dir / "series.json"
    last_run_path = data_dir / "last_run.json"
    today = datetime.now(KST).date()

    merged = store.load_series(series_path)
    summary = {
        "run_at": datetime.now(KST).isoformat(),
        "collectors": {},
        "conflicts": [],
        "errors": [],
    }

    for name, collect_fn in collectors.items():
        try:
            candidates = collect_fn(today)
            result = store.upsert(merged, candidates)
            merged = result.records
            summary["collectors"][name] = {
                "ok": True, "fetched": len(candidates),
                "added": len(result.added), "updated": len(result.updated),
            }
        except Exception as exc:
            summary["collectors"][name] = {
                "ok": False, "fetched": 0, "added": 0, "updated": 0,
            }
            summary["errors"].append(f"{name}: {type(exc).__name__}: {exc}")

    # 수기 입력은 마지막에 얹어 수집 결과를 이긴다.
    manual = load_manual(data_dir)
    if manual:
        merged = store.upsert(merged, manual).records

    store.save_series(series_path, merged)
    last_run_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary["collectors"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
