"""전망 근거를 LLM 으로 골라 rationales.json 에 넣는다.

CI 가 이 도구를 부르지 않는다. 근거는 회차당 한 번 정해지면 되는 것이라
매일 돌 이유가 없고, 도구로 두면 LLM 이 죽든 키가 만료되든 매일 도는
수치 수집과 배포는 그대로 돈다.

이미 있는 항목은 덮지 않는다 — 사람이 문장을 다듬었을 수 있다. 일부러
다시 만들려면 --refresh 로 대상을 명시해야 한다.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from domains.forecast.pipeline import llm_select, llm_verify, rationale
from domains.forecast.pipeline import rationale_store as rs
from domains.forecast.pipeline.documents import SOURCES

DATA_DIR = Path(__file__).resolve().parent.parent / "domains" / "forecast" / "data"


@dataclass
class Report:
    saved: int = 0
    skipped: int = 0
    rejected: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)


def run(data_dir, *, sources=None, select=None, only=None, refresh=()) -> Report:
    sources = SOURCES if sources is None else sources
    select = select or llm_select.select
    path = Path(data_dir) / "rationales.json"
    existing, load_error = rs.load_or_empty(path)
    rep = Report()
    if load_error:
        rep.failures.append(f"rationales.json 을 읽지 못했다: {load_error}")
        return rep  # 사람이 고치던 파일을 기계 파일로 덮지 않는다

    if refresh:
        existing = [r for r in existing if r.key not in refresh]

    fresh: list[rs.Rationale] = []
    for name, listing in sources.items():
        if only and name not in only:
            continue
        try:
            listed_all = listing()
        except Exception as exc:
            rep.failures.append(f"{name} 목록: {type(exc).__name__}: {exc}")
            continue
        for listed in listed_all:
            try:
                source_url, pages = listed.fetch_pages()
                picked = select(listed.org, listed.title, listed.indicators, pages)
            except Exception as exc:
                rep.failures.append(
                    f"{name} {listed.title}: {type(exc).__name__}: {exc}")
                continue
            for p in picked:
                if p.indicator not in listed.indicators:
                    rep.rejected.append(
                        f"{listed.org} {listed.title} {p.indicator}: "
                        "이 기관이 전망하지 않는 지표다")
                    continue
                page_text = pages[p.source_page - 1] if 0 < p.source_page <= len(pages) else ""
                try:
                    text = llm_verify.verify(p.text, page_text)
                except llm_verify.Rejected as exc:
                    rep.rejected.append(
                        f"{listed.org} {listed.title} {p.indicator}: {exc.reason}")
                    continue
                fresh.append(rs.Rationale(
                    org=listed.org, published_at=listed.published_at,
                    indicator=p.indicator, text=text, tags=rationale.tags_for(text),
                    source_url=source_url, source_page=p.source_page))

    merged = rs.merge(existing, fresh)
    rep.saved = len(merged) - len(existing)
    rep.skipped = len(fresh) - rep.saved
    if merged != existing:
        rs.save(path, merged)
    return rep


def _parse_refresh(item: str) -> tuple[str, date, str]:
    """'<기관>:<발표일>:<지표>' 를 rs.Rationale.key 와 같은 모양으로 읽는다.

    발표일에 ':' 가 없으므로 최대 두 번만 자른다("KDI:2026-08-19:emp_change").
    """
    parts = item.split(":", 2)
    if len(parts) != 3:
        raise ValueError(f"'<기관>:<발표일>:<지표>' 형식이 아니다: {item!r}")
    org, date_str, indicator = parts
    try:
        published_at = date.fromisoformat(date_str)
    except ValueError as exc:
        raise ValueError(f"발표일을 읽지 못했다({date_str!r}) — YYYY-MM-DD 로 적는다") from exc
    return (org, published_at, indicator)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only", action="append", default=None, metavar="기관",
        help="이 기관만 수집한다(반복 가능) — 예: --only kdi")
    parser.add_argument(
        "--refresh", action="append", default=[], metavar="기관:발표일:지표",
        help="이미 있는 근거를 다시 만든다(반복 가능하고, 명시한 대상만 지운다) "
             "— 예: --refresh KDI:2026-08-19:emp_change")
    args = parser.parse_args(argv)

    unknown = [name for name in (args.only or []) if name not in SOURCES]
    if unknown:
        print(f"모르는 기관: {unknown} — 쓸 수 있는 것: {sorted(SOURCES)}")
        return 1

    try:
        refresh = {_parse_refresh(item) for item in args.refresh}
    except ValueError as exc:
        print(f"--refresh 를 읽지 못했다: {exc}")
        return 1

    rep = run(DATA_DIR, only=args.only, refresh=refresh)

    for line in rep.lines:
        print(line)
    print(f"\n요약: 저장 {rep.saved}건 / 건너뜀 {rep.skipped}건 / "
          f"거절 {len(rep.rejected)}건 / 실패 {len(rep.failures)}건")
    for line in rep.rejected:
        print(f"  거절 — {line}")
    for line in rep.failures:
        print(f"  실패 — {line}")
    return 1 if rep.failures else 0


if __name__ == "__main__":
    # 워크플로가 아니라 사람이 콘솔에서 돌린다 — 로컬 콘솔은 UTF-8 이
    # 아닐 수 있다(윈도우 cp949).
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
