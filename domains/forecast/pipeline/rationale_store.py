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


def load_or_empty(path: Path | str) -> tuple[list[Rationale], str | None]:
    """읽을 수 없으면 빈 리스트와 그 이유를 준다 — 터지지 않는다.

    설계 4.3 은 **사람이 이 파일을 열어 문장을 고치는 것**을 전제한다. 그
    말은 손으로 만든 오류(따옴표 하나 빠뜨림, 끝 쉼표, `"source_page":
    "열 번째 쪽"`)가 이 파일의 현실적인 입력이라는 뜻이다. `load` 가 그대로
    터지면 그 오류 하나가 그날 수집 전체를 끌고 내려간다 — 수치도 못 쓰고
    `last_run.json` 도 안 남아 무슨 일이 있었는지조차 모르게 된다. 이
    브랜치가 내내 붙들어 온 우선순위(설계 §9: "근거 때문에 수치를 잃는
    것이 더 나쁘다")와 정반대다. 화면 쪽 `app.js` 는 같은 파일을 이미 이렇게
    다룬다 — 못 읽으면 근거 없이 그린다.

    돌려주는 두 번째 값은 **저장 여부를 가르는 신호**다. 못 읽은 파일에
    새 근거를 덮어쓰면 사람이 고치던 편집물을 우리가 지우는 셈이라, 호출부는
    이 값이 None 이 아닐 때 `save` 를 건너뛴다. 다음 실행이 파일을 고친 뒤
    다시 모으면 된다 — 근거는 언제든 다시 뽑을 수 있지만 사람이 손댄
    문장은 그렇지 않다.

    `forecasts.json` 에는 같은 처리를 하지 않는다 — 그건 기계만 쓰는
    파일이라 손으로 고칠 일이 없고, 못 읽는다면 그건 진짜 사고다.
    """
    try:
        return load(path), None
    except Exception as exc:
        return [], f"{type(exc).__name__}: {exc}"


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
