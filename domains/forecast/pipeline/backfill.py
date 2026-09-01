"""지나간 회차를 1회성으로 소급 수집한다.

일상 수집기(`collect.main`)는 최신 회차 하나만 본다. 그것이 맞는 동작이지만,
아카이브를 시작하기 전에 이미 지나간 회차는 그 경로로 영원히 들어오지 않는다.
이 모듈이 그 구멍을 메운다. CI 에 넣지 않는다 — 사람이 필요할 때 한 번 돌린다.

중복은 `store.merge` 가 id 로 걸러낸다. 값 비교로 거르지 않는다 — 값이 그대로인
회차도 그 기관이 그때 그렇게 전망했다는 기록이므로 남겨야 한다.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, NamedTuple

from . import rationale_store as rs, store
from .collectors import bok, imf, kdi, keis, kiet, kli, oecd, oecd_interim
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
    # 근거 실패는 수치 백필의 성패(failed/failures)와 별도로 센다 — 근거는
    # 곁가지고, 근거가 죽었다고 그 회차의 수치 백필까지 실패로 세면 안 된다.
    rationale_errors: list[str] = field(default_factory=list)


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


def imf_rounds() -> list[Round]:
    """보관된 지난 회차. 현행 회차는 일상 수집기가 발표일과 함께 가져온다."""
    return [
        Round(label, pub, lambda label=label: imf.collect_vintage(label))
        for label, (_, _, pub) in imf.VINTAGES.items()
    ]


def kiet_rounds() -> list[Round]:
    return [
        Round(issue.title, issue.published_at, lambda issue=issue: kiet.collect_issue(issue))
        for issue in kiet.list_issues()
    ]


def kli_rounds() -> list[Round]:
    return [
        Round(issue.title, issue.published_at, lambda issue=issue: kli.collect_issue(issue))
        for issue in kli.list_issues()
    ]


def kdi_rounds() -> list[Round]:
    # 드롭다운은 1982년까지 이어진다. 백필 커트라인(SINCE)의 연도를 그대로
    # 넘겨, 그보다 뚜렷하게 이전인 회차는 kdi.list_issues() 가 페이지를
    # 열어보지도 않고 미리 거르게 한다.
    return [
        Round(issue.title, issue.published_at, lambda issue=issue: kdi.collect_issue(issue))
        for issue in kdi.list_issues(since_year=SINCE.year)
    ]


def keis_rounds() -> list[Round]:
    """고용동향브리프는 전망을 싣지 않는 호가 대부분이다.

    그런 호는 `collect_issue` 가 빈 리스트를 주고 `run` 이 '건너뜀' 으로
    적는다 — 실패가 아니다.
    """
    return [
        Round(item.issue.title, item.issue.published_at,
              lambda item=item: keis.collect_issue(item))
        for item in keis.list_issues()
    ]


SOURCES: dict[str, Callable[[], list[Round]]] = {
    "oecd": oecd_rounds,
    "oecd_interim": oecd_interim_rounds,
    "bok": bok_rounds,
    "kli": kli_rounds,
    "kdi": kdi_rounds,
    "kiet": kiet_rounds,
    "imf": imf_rounds,
    "keis": keis_rounds,
}


def bok_rationale_rounds() -> list[Round]:
    return [
        Round(issue.title, issue.published_at,
              lambda issue=issue: bok.collect_issue_rationales(issue))
        for issue in bok.list_issues()
    ]


def oecd_interim_rationale_rounds() -> list[Round]:
    return [
        Round(label, pub, lambda label=label: oecd_interim.collect_edition_rationales(label))
        for label, (pub, _) in sorted(oecd_interim.EDITIONS.items(), key=lambda kv: kv[1][0])
    ]


def kiet_rationale_rounds() -> list[Round]:
    return [
        Round(issue.title, issue.published_at,
              lambda issue=issue: kiet.collect_issue_rationales(issue))
        for issue in kiet.list_issues()
    ]


def kli_rationale_rounds() -> list[Round]:
    return [
        Round(issue.title, issue.published_at,
              lambda issue=issue: kli.collect_issue_rationales(issue))
        for issue in kli.list_issues()
    ]


def kdi_rationale_rounds() -> list[Round]:
    return [
        Round(issue.title, issue.published_at,
              lambda issue=issue: kdi.collect_issue_rationales(issue))
        for issue in kdi.list_issues(since_year=SINCE.year)
    ]


def keis_rationale_rounds() -> list[Round]:
    return [
        Round(item.issue.title, item.issue.published_at,
              lambda item=item: keis.collect_issue_rationales(item))
        for item in keis.list_issues()
    ]


# imf·oecd 는 없다 — API 로 숫자만 읽어 근거로 삼을 본문이 없다. run() 은
# sources 에 있는 이름이라도 여기 없으면 그냥 건너뛴다(부재를 견딘다).
RATIONALE_SOURCES: dict[str, Callable[[], list[Round]]] = {
    "oecd_interim": oecd_interim_rationale_rounds,
    "bok": bok_rationale_rounds,
    "kli": kli_rationale_rounds,
    "kdi": kdi_rationale_rounds,
    "kiet": kiet_rationale_rounds,
    "keis": keis_rationale_rounds,
}


def run(sources: dict[str, Callable[[], list[Round]]] = None,
        rationale_sources: dict[str, Callable[[], list[Round]]] = None, *,
        data_dir: Path = DATA_DIR, since: date = SINCE,
        only: list[str] | None = None) -> Report:
    sources = SOURCES if sources is None else sources
    # 기본값을 빈 dict 로 둔다 — sources 처럼 실제 레지스트리를 기본값으로
    # 하면, sources 만 바꿔 끼우는 기존 테스트들이 이름이 겹치는 순간(예:
    # "bok"·"kdi") 모르게 네트워크를 타 버린다. 실제 운영은 main() 이
    # RATIONALE_SOURCES 를 명시적으로 넘긴다.
    rationale_sources = {} if rationale_sources is None else rationale_sources
    path = Path(data_dir) / "forecasts.json"
    rationales_path = Path(data_dir) / "rationales.json"
    # forecasts.json 은 기계만 쓰는 파일이라 못 읽으면 그건 진짜 사고다 —
    # 여기서 감싸지 않는다(rationale_store.load_or_empty 문서주석 참고).
    records = store.load_forecasts(path)
    rationales, rationale_load_error = rs.load_or_empty(rationales_path)
    existing_rationales = list(rationales)  # 내용 비교용 스냅샷
    report = Report()
    if rationale_load_error is not None:
        report.rationale_errors.append(
            f"rationales.json 을 읽지 못해 이번 실행은 근거를 비운 채로 "
            f"진행한다(저장도 건너뛴다) — {rationale_load_error}")

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

        # 근거 회차 목록도 (라벨, 발표일) 로 찾아 매칭한다 — 같은 list_issues()
        # 에서 나온 값이라 forecast Round 와 키가 같다. 근거 쪽이 아예 없는
        # 기관(imf·oecd)이나, 목록 자체가 실패한 경우는 빈 매칭으로 둔다 —
        # 수치 백필은 그대로 진행돼야 한다.
        rationale_by_key: dict[tuple[str, date], Round] = {}
        list_rationale_rounds = rationale_sources.get(name)
        if list_rationale_rounds is not None:
            try:
                rationale_by_key = {
                    (r.label, r.published_at): r for r in list_rationale_rounds()
                }
            except Exception as exc:
                report.rationale_errors.append(f"{name}: 근거 회차 목록 {_reason(exc)}")

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

            rationale_round = rationale_by_key.get((rnd.label, rnd.published_at))
            if rationale_round is None:
                continue
            try:
                rationale_candidates = rationale_round.fetch()
            except Exception as exc:
                # 근거 실패는 이 회차의 수치 백필(위의 saved/skipped)을 건드리지
                # 않는다 — 수치가 본체다.
                report.rationale_errors.append(f"{name}: 근거({rnd.label}) {_reason(exc)}")
                continue
            rationales = rs.merge(rationales, rationale_candidates)

    # 과거 회차가 나중에 들어오므로, 먼저 저장돼 있던 회차의 수정폭이 비어 있다.
    store.save_forecasts(path, store.recompute_revisions(records))
    # 개수가 아니라 내용으로 비교한다 — merge 가 잘못 짜여 있는 값을 덮어써도
    # 개수는 그대로일 수 있는데(같은 키, 다른 문장), 개수만 보면 그 사고를
    # 놓치고 저장하지 않아 파일이 우연히 이전 그대로인 것처럼 보인다.
    # 못 읽은 파일에는 쓰지 않는다 — 사람이 고치던 편집물을 우리가 지우게
    # 된다(rationale_store.load_or_empty 문서주석).
    if rationale_load_error is None and rationales != existing_rationales:
        rs.save(rationales_path, rationales)
    return report


def _reason(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    unknown = [name for name in argv if name not in SOURCES]
    if unknown:
        print(f"모르는 기관: {unknown} — 쓸 수 있는 것: {sorted(SOURCES)}")
        return 1
    report = run(rationale_sources=RATIONALE_SOURCES, only=argv or None)
    for line in report.lines:
        print(line)
    print(f"\n요약: 시도 {report.attempted} / 저장 {report.saved}건 / "
          f"건너뜀 {report.skipped} / 실패 {report.failed}")
    for name, label, reason in report.failures:
        print(f"  실패 — {name} {label}: {reason}")
    for line in report.rationale_errors:
        print(f"  근거 실패 — {line}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
