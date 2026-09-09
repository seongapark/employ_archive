"""sources/raw/ 읽기·병합·저장. 판정은 하지 않는다."""
from __future__ import annotations

import json
from pathlib import Path

from .models import RawReport

RAW_ROOT = Path(__file__).resolve().parent.parent / 'sources' / 'raw'


def raw_path(board_id: str, org: str, root: Path | str | None = None) -> Path:
    return Path(root or RAW_ROOT) / org / f'{board_id}.json'


def load_raw(path: Path | str) -> list[RawReport]:
    p = Path(path)
    if not p.exists():
        return []
    return [RawReport.model_validate(r)
            for r in json.loads(p.read_text(encoding='utf-8'))]


def save_raw(path: Path | str, records: list[RawReport]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = [r.model_dump(mode='json')
            for r in sorted(records, key=lambda r: r.id)]
    p.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n',
                 encoding='utf-8')


def _same(a: RawReport, b: RawReport) -> bool:
    """collected_at 을 뺀 나머지가 같으면 같은 관측이다."""
    x = a.model_dump(exclude={'collected_at'})
    y = b.model_dump(exclude={'collected_at'})
    return x == y


def upsert(existing: list[RawReport],
           incoming: list[RawReport]) -> tuple[list[RawReport], list[str]]:
    by_id = {r.id: r for r in existing}
    added: list[str] = []
    for rec in incoming:
        old = by_id.get(rec.id)
        if old is None:
            by_id[rec.id] = rec
            added.append(rec.id)
        elif not _same(old, rec):
            by_id[rec.id] = rec
    return sorted(by_id.values(), key=lambda r: r.id), added


def load_all_raw(root: Path | str | None = None) -> list[RawReport]:
    base = Path(root or RAW_ROOT)
    if not base.is_dir():
        return []
    out: list[RawReport] = []
    for p in sorted(base.rglob('*.json')):
        out.extend(load_raw(p))
    return out
