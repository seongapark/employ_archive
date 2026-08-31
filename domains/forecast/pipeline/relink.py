"""이미 저장된 레코드의 원문 링크만 고치는 일회성 도구.

store.merge 는 값이 같은 레코드를 건너뛴다 — 같은 값이면 같은 관측이고, 수집기가
돌 때마다 메타데이터가 흔들리면 안 되기 때문이다. 그 규칙은 옳다. 그래서 백필을
다시 돌려도 옛 레코드의 링크는 API 주소로 남는다.

이 도구가 그 구멍을 메운다. CI 에 넣지 않는다 — 사람이 한 번 돌린다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .models import ForecastRecord

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass
class RelinkResult:
    records: list[ForecastRecord]
    changed: int = 0
    unresolved: list[tuple[str, str]] = field(default_factory=list)


def relink(records: list[ForecastRecord],
           resolvers: dict[str, Callable[[ForecastRecord], str]]) -> RelinkResult:
    """기관별 해결자로 원문 주소를 구해 링크만 바꾼다.

    수치·식별자·수정폭은 건드리지 않는다. 주소를 못 구한 레코드는 그대로 두고
    몇 건인지 남긴다 — 조용히 빠뜨리면 무엇이 안 고쳐졌는지 알 수 없다.
    """
    result = RelinkResult(records=[])
    cache: dict[tuple[str, str], str] = {}
    for rec in records:
        resolve = resolvers.get(rec.org)
        if resolve is None:
            result.records.append(rec)
            continue
        key = (rec.org, rec.report_title)
        try:
            url = cache[key] if key in cache else resolve(rec)
        except Exception as exc:
            result.unresolved.append((rec.id, f"{type(exc).__name__}: {exc}"))
            result.records.append(rec)
            continue
        cache[key] = url
        result.records.append(rec.model_copy(update={"source_url": url, "landing_url": url}))
        result.changed += 1
    return result


_IMF_LABEL = re.compile(r"(?:Update\s+)?(January|February|March|April|May|June|"
                        r"July|August|September|October|November|December)\s+(\d{4})",
                        re.IGNORECASE)


def _imf_label(report_title: str) -> str:
    """'IMF World Economic Outlook, April 2026' 에서 'April 2026' 을 뗀다.

    Update 회차는 제목에 Update 가 들어가므로 라벨에도 남긴다 — imf.report_url
    이 그 낱말로 슬러그를 가른다.
    """
    m = _IMF_LABEL.search(report_title)
    if m is None:
        raise ValueError(f"IMF 회차 제목에서 라벨을 읽지 못했다: {report_title!r}")
    prefix = "Update " if "update" in report_title.lower() else ""
    return f"{prefix}{m.group(1)} {m.group(2)}"


def _oecd_resolver(rec: ForecastRecord) -> str:
    """OECD Interim 은 이미 보고서 PDF 를 가리키므로 건드리지 않는다."""
    if "Interim" in rec.report_title:
        raise ValueError("OECD Interim 레코드는 대상이 아니다 — 이미 보고서를 가리킨다")
    from .collectors import oecd
    return oecd.report_url(oecd.edition_number(rec.report_title))


def main(data_dir: Path = DATA_DIR) -> int:
    from .collectors import imf, oecd
    from . import store

    path = Path(data_dir) / "forecasts.json"
    before = store.load_forecasts(path)
    resolvers = {
        "IMF": lambda r: imf.report_url(_imf_label(r.report_title), r.published_at),
        "OECD": _oecd_resolver,
    }
    result = relink(before, resolvers)

    # 링크만 바꾸는 도구다. 수치가 한 건이라도 움직였으면 저장하지 않는다.
    same = {(r.id, r.value) for r in before} == {(r.id, r.value) for r in result.records}
    if not same:
        print("::error::수치가 바뀌었다 — 저장하지 않는다")
        return 1

    store.save_forecasts(path, result.records)
    print(f"링크 교체 {result.changed}건 / 못 찾음 {len(result.unresolved)}건")
    for rec_id, why in result.unresolved:
        print(f"  못 찾음 {rec_id}: {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
