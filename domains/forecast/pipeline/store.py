from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .models import ForecastRecord


@dataclass
class MergeResult:
    records: list[ForecastRecord]
    added: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


def load_forecasts(path: Path | str) -> list[ForecastRecord]:
    p = Path(path)
    if not p.exists():
        return []
    raw = json.loads(p.read_text(encoding="utf-8"))
    return [ForecastRecord.model_validate(row) for row in raw]


def save_forecasts(path: Path | str, records: list[ForecastRecord]) -> None:
    ordered = sorted(records, key=lambda r: (r.published_at.isoformat(), r.id))
    rows = [r.model_dump(mode="json") for r in ordered]
    Path(path).write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def latest_record(records, org, indicator, target_year, target_period="annual", before=None):
    matches = [
        r for r in records
        if r.org == org and r.indicator == indicator
        and r.target_year == target_year and r.target_period == target_period
    ]
    if before is not None:
        matches = [r for r in matches if r.published_at < before]
    return max(matches, key=lambda r: r.published_at) if matches else None


def _day_id(cand: ForecastRecord) -> str:
    suffix = "" if cand.target_period == "annual" else f"-{cand.target_period}"
    return (
        f"{cand.org.lower()}-{cand.published_at:%Y-%m-%d}-"
        f"{cand.indicator}-{cand.target_year}{suffix}"
    )


def _add(result: MergeResult, by_id: dict[str, ForecastRecord],
         cand: ForecastRecord, new_id: str | None = None) -> None:
    if new_id is not None:
        cand = cand.model_copy(update={"id": new_id})
    prev = latest_record(
        result.records, cand.org, cand.indicator,
        cand.target_year, cand.target_period,
        before=cand.published_at,
    )
    if prev is not None:
        cand = cand.model_copy(update={
            "prev_value": prev.value,
            "revision": round(cand.value - prev.value, 2),
        })
    result.records.append(cand)
    by_id[cand.id] = cand
    result.added.append(cand.id)


def merge(existing: list[ForecastRecord], new: list[ForecastRecord]) -> MergeResult:
    result = MergeResult(records=list(existing))
    by_id = {r.id: r for r in result.records}
    for cand in sorted(new, key=lambda r: r.published_at):
        stored = by_id.get(cand.id)
        if stored is not None:
            if stored.value == cand.value:
                result.skipped.append(cand.id)
                continue
            # Same-month id already taken by a different value: this is a
            # same-month revision (e.g. a second edition within the month).
            # Re-id with day precision instead of discarding it, so the
            # revision is captured rather than silently dropped.
            day_id = _day_id(cand)
            day_stored = by_id.get(day_id)
            if day_stored is not None:
                if day_stored.value == cand.value:
                    result.skipped.append(day_id)
                else:
                    result.conflicts.append(
                        f"{day_id}: stored={day_stored.value} incoming={cand.value}"
                    )
                continue
            _add(result, by_id, cand, new_id=day_id)
            continue
        _add(result, by_id, cand)
    return result
