"""근거를 한 번만 저장한다.

레코드마다 복사하지 않는다. 같은 문장이 연간·상반기·하반기에 흩어지면 문장을
손볼 때 몇 군데를 고쳐야 하는지 알 수 없다. 여기서는 (기관, 발표일, 지표) 하나에
한 줄이라 사람이 직접 열어 고칠 수 있다.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field


class Rationale(BaseModel):
    org: str
    published_at: date
    indicator: str
    text: str
    tags: list[str] = Field(default_factory=list)
    source_url: str
    source_page: int | None = None

    @property
    def key(self) -> tuple[str, date, str]:
        return (self.org, self.published_at, self.indicator)


def load(path: Path | str) -> list[Rationale]:
    p = Path(path)
    if not p.exists():
        return []
    return [Rationale.model_validate(row)
            for row in json.loads(p.read_text(encoding="utf-8"))]


def save(path: Path | str, items: list[Rationale]) -> None:
    ordered = sorted(items, key=lambda r: (r.published_at.isoformat(), r.org, r.indicator))
    Path(path).write_text(
        json.dumps([r.model_dump(mode="json") for r in ordered],
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")


def merge(existing: list[Rationale], new: list[Rationale]) -> list[Rationale]:
    """없는 것만 더한다.

    이미 있는 항목은 그대로 둔다 — 사람이 문장을 다듬었을 수 있고, 재수집이
    그것을 조용히 되돌리면 손댈 이유가 사라진다.

    new 안에서 같은 키가 여럿이면 첫 번째만 더한다 — 보고서의 페이지를 따로
    처리하면 같은 지표에 대해 두 문장이 나올 수 있는데, key 는 한 항목을
    가리키는 것이지 여럿을 가리키는 게 아니다. 먼저 온 것(보고서의 앞쪽
    페이지)을 남긴다.
    """
    seen = {r.key for r in existing}
    kept: list[Rationale] = []
    for r in new:
        if r.key in seen:
            continue
        seen.add(r.key)
        kept.append(r)
    return list(existing) + kept
