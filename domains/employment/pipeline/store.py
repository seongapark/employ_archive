"""시계열 적재. 같은 id 는 덮어쓴다 — 실적 통계는 과거 수치가 개정된다."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .models import SeriesRecord


@dataclass
class UpsertResult:
    records: list[SeriesRecord]
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)


def load_series(path: Path | str) -> list[SeriesRecord]:
    p = Path(path)
    if not p.exists():
        return []
    raw = json.loads(p.read_text(encoding="utf-8"))
    records = [SeriesRecord.model_validate(row) for row in raw]
    seen: set[str] = set()
    duplicates = sorted({r.id for r in records if r.id in seen or seen.add(r.id)})
    if duplicates:
        raise ValueError(f"id 가 중복된 레코드가 있다: {', '.join(duplicates)}")
    return records


def save_series(path: Path | str, records: list[SeriesRecord]) -> None:
    ordered = sorted(records, key=lambda r: (r.period, r.source, r.id))
    rows = [r.model_dump(mode="json") for r in ordered]
    Path(path).write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def upsert(existing: list[SeriesRecord],
           incoming: list[SeriesRecord]) -> UpsertResult:
    by_id = {r.id: r for r in existing}
    result = UpsertResult(records=list(existing))

    for cand in incoming:
        stored = by_id.get(cand.id)
        if stored is None:
            result.records.append(cand)
            by_id[cand.id] = cand
            result.added.append(cand.id)
            continue
        # 더 오래된 발표본이 뒤늦게 도착해도 최신 수치를 덮지 않는다.
        # 조용히 넘어가지 않는다 — 여기서 흔적을 안 남기면 released_at 이
        # 거꾸로 도는 버그(예: 회차 오탐지)가 added:0, updated:0 인 초록
        # 실행으로 둔갑해 아무 데도 드러나지 않는다.
        if cand.released_at < stored.released_at:
            result.rejected.append(cand.id)
            continue
        # 수치가 같으면 같은 관측이다. released_at·release_url 이 달라져도
        # 갱신으로 세지 않는다 — 메타데이터 변경은 화면에 아무 차이를 만들지 않는다.
        if (stored.value, stored.yoy, stored.status) == (cand.value, cand.yoy, cand.status):
            result.unchanged.append(cand.id)
            continue
        for index, existing_record in enumerate(result.records):
            if existing_record is stored:
                result.records[index] = cand
                break
        by_id[cand.id] = cand
        result.updated.append(cand.id)

    return result
