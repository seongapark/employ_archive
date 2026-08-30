"""지나간 회차를 1회성으로 소급 수집한다.

일상 수집기(`collect.main`)는 최신 회차 하나만 본다. 그것이 맞는 동작이지만,
아카이브를 시작하기 전에 이미 지나간 회차는 그 경로로 영원히 들어오지 않는다.
이 모듈이 그 구멍을 메운다. CI 에 넣지 않는다 — 사람이 필요할 때 한 번 돌린다.

`collect.drop_unchanged` 를 쓰지 않는다. 그것은 전역 최신값과 비교하므로,
과거 회차 값이 이미 저장된 최신 회차와 같으면 조용히 버린다. 백필에는 틀린
규칙이다. 중복은 `store.merge` 가 id 로 걸러낸다.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, NamedTuple

from . import store
from .collectors import bok, kli, oecd, oecd_interim
from .models import ForecastRecord

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# 2026년 전망이 처음 등장한 시점(한국은행 2024년 11월호가 2025·2026년을 전망).
# 자동 판정 대신 날짜로 못 박는다 — 옛 회차는 서식이 달라 파싱이 깨질 수 있는데,
# 자동 판정은 그 실패와 '회차 없음'을 구별하지 못해 조용히 덜 가져온다.
SINCE = date(2024, 11, 1)


class Round(NamedTuple):
    label: str
    published_at: date
    fetch: Callable[[], list[ForecastRecord]]


@dataclass
class Report:
    attempted: int = 0
    saved: int = 0
    skipped: int = 0
    failed: int = 0
    lines: list[str] = field(default_factory=list)
    failures: list[tuple[str, str, str]] = field(default_factory=list)


def oecd_rounds() -> list[Round]:
    return [
        Round(f"EO {no}", pub, lambda no=no: oecd.collect_edition(no))
        for no, pub in sorted(oecd.EDITIONS.items(), key=lambda kv: kv[1], reverse=True)
    ]


def bok_rounds() -> list[Round]:
    return [
        Round(issue.title, issue.published_at, lambda issue=issue: bok.collect_issue(issue))
        for issue in bok.list_issues()
    ]


def oecd_interim_rounds() -> list[Round]:
    return [
        Round(label, pub, lambda label=label: oecd_interim.collect_edition(label))
        for label, (pub, _) in sorted(oecd_interim.EDITIONS.items(), key=lambda kv: kv[1][0])
    ]


def kli_rounds() -> list[Round]:
    return [
        Round(issue.title, issue.published_at, lambda issue=issue: kli.collect_issue(issue))
        for issue in kli.list_issues()
    ]


SOURCES: dict[str, Callable[[], list[Round]]] = {
    "oecd": oecd_rounds,
    "oecd_interim": oecd_interim_rounds,
    "bok": bok_rounds,
    "kli": kli_rounds,
}


def run(sources: dict[str, Callable[[], list[Round]]] = None, *,
        data_dir: Path = DATA_DIR, since: date = SINCE,
        only: list[str] | None = None) -> Report:
    sources = SOURCES if sources is None else sources
    path = Path(data_dir) / "forecasts.json"
    records = store.load_forecasts(path)
    report = Report()

    for name, list_rounds in sources.items():
        if only is not None and name not in only:
            continue
        try:
            rounds = list_rounds()
        except Exception as exc:
            report.failed += 1
            report.failures.append((name, "회차 목록", _reason(exc)))
            report.lines.append(f"{name}: 회차 목록 실패 — {_reason(exc)}")
            continue

        wanted = [r for r in rounds if r.published_at >= since]
        report.lines.append(f"{name}: {len(wanted)}회차 시도 (전체 {len(rounds)})")
        for rnd in sorted(wanted, key=lambda r: r.published_at):
            report.attempted += 1
            try:
                candidates = rnd.fetch()
            except Exception as exc:
                report.failed += 1
                report.failures.append((name, rnd.label, _reason(exc)))
                report.lines.append(f"  {rnd.published_at}  {rnd.label}  실패 — {_reason(exc)}")
                continue
            result = store.merge(records, candidates)
            records = result.records
            if result.added:
                report.saved += len(result.added)
                report.lines.append(f"  {rnd.published_at}  {rnd.label}  {len(result.added)}건")
            else:
                report.skipped += 1
                report.lines.append(f"  {rnd.published_at}  {rnd.label}  건너뜀 (이미 있음)")

    # 과거 회차가 나중에 들어오므로, 먼저 저장돼 있던 회차의 수정폭이 비어 있다.
    store.save_forecasts(path, store.recompute_revisions(records))
    return report


def _reason(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    unknown = [name for name in argv if name not in SOURCES]
    if unknown:
        print(f"모르는 기관: {unknown} — 쓸 수 있는 것: {sorted(SOURCES)}")
        return 1
    report = run(only=argv or None)
    for line in report.lines:
        print(line)
    print(f"\n요약: 시도 {report.attempted} / 저장 {report.saved}건 / "
          f"건너뜀 {report.skipped} / 실패 {report.failed}")
    for name, label, reason in report.failures:
        print(f"  실패 — {name} {label}: {reason}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
