from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from . import announce, calendar, http, report, store, watch
from .collectors import bok, imf, kdi, keis, kiet, kli, moef, oecd, oecd_interim
from .models import ForecastRecord

KST = timezone(timedelta(hours=9))
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
# 봇 차단(http.Blocked)은 이 날수까지 오류로 올리지 않는다. 그동안 발표가 나와
# 회차가 빠지면 watch 가 따로 오류를 낸다 — 유예가 누락을 가리지는 않는다.
BLOCKED_GRACE_DAYS = 7

COLLECTORS: dict[str, Callable[[date], list[ForecastRecord]]] = {
    "oecd": oecd.collect,
    "oecd_interim": oecd_interim.collect,
    "imf": imf.collect,
    "imf_update": imf.collect_update,
    "bok": bok.collect,
    "kdi": kdi.collect,
    "kli": kli.collect,
    "kiet": kiet.collect,
    "keis": keis.collect,
    "moef": moef.collect,
}


def main(data_dir: Path = DATA_DIR,
         collectors: dict[str, Callable[[date], list[ForecastRecord]]] = COLLECTORS,
         check: Callable[[list[ForecastRecord], date], list[str]] | None = None,
         partial: bool = False,
         ) -> int:
    forecasts_path = data_dir / "forecasts.json"
    last_run_path = data_dir / "last_run.json"
    today = datetime.now(KST).date()

    # forecasts.json 은 기계만 쓰는 파일이라 못 읽으면 그건 진짜 사고다 —
    # 여기서 감싸지 않는다.
    existing = store.load_forecasts(forecasts_path)
    merged = existing
    previous = (json.loads(last_run_path.read_text(encoding="utf-8"))
                if last_run_path.exists() else {})
    # 수집기마다 차단이 처음 보인 날. 차단이 이어지는 동안 지난 실행에서 물려받는다.
    blocked_since: dict[str, str] = previous.get("blocked", {})
    summary = {
        "run_at": datetime.now(KST).isoformat(),
        "collectors": {},
        "conflicts": [],
        "errors": [],
        "warnings": [],
        "blocked": {},
    }

    for name, collect_fn in collectors.items():
        try:
            candidates = collect_fn(today)
            # 값이 그대로여도 버리지 않는다. published_at 이 발표일이 된 뒤로 id 가
            # 회차마다 고정돼, 값 비교로 거르면 그 회차가 통째로 사라진다.
            # 같은 회차를 다시 받은 경우는 store.merge 가 id 로 걸러낸다.
            result = store.merge(merged, candidates)
            merged = result.records
            summary["conflicts"].extend(result.conflicts)
            summary["collectors"][name] = {
                "ok": True, "fetched": len(candidates), "added": len(result.added),
            }
        except http.Blocked as exc:
            since = blocked_since.get(name, today.isoformat())
            summary["blocked"][name] = since
            summary["collectors"][name] = {"ok": False, "fetched": 0, "added": 0, "blocked": True}
            days = (today - date.fromisoformat(since)).days
            if days >= BLOCKED_GRACE_DAYS:
                summary["errors"].append(f"{name}: {since} 부터 {days}일째 봇 차단 — {exc}")
            else:
                summary["warnings"].append(f"{name}: 봇 차단 {days}일째(유예 {BLOCKED_GRACE_DAYS}일) — {exc}")
        except report.PartialFailure as exc:
            # 옛 회차 하나가 실패해도 새로 받은 회차는 저장한다.
            result = store.merge(merged, exc.records)
            merged = result.records
            summary["collectors"][name] = {
                "ok": False, "fetched": len(exc.records), "added": len(result.added),
            }
            summary["errors"].append(f"{name}: {exc}")
        except Exception as exc:
            # last_run.json 은 저장소에 커밋된다 — 트레이스백을 담으면 돌린 사람의
            # 절대경로까지 함께 실린다. 무엇이 왜 실패했는지만 한 줄로 남긴다.
            summary["collectors"][name] = {"ok": False, "fetched": 0, "added": 0}
            summary["errors"].append(f"{name}: {type(exc).__name__}: {exc}")

    # 감시와 공지일 갱신은 수집기를 주입한 시험에서는 꺼진다 — 시험이 네트워크에 나가면 안 된다.
    if collectors is COLLECTORS:
        try:
            added = announce.refresh(data_dir / "schedule.json", today, lambda url: http.get(url).text,
                                     summary["warnings"])
            summary["collectors"]["announce"] = {"ok": True, "fetched": 0, "added": added}
        except Exception as exc:
            summary["collectors"]["announce"] = {"ok": False, "fetched": 0, "added": 0}
            summary["errors"].append(f"announce: {type(exc).__name__}: {exc}")
    if collectors is COLLECTORS:
        try:
            # 공지일 갱신 뒤에 만든다 — 그날 새로 공지된 날짜가 일정표에 바로 붙게.
            calendar.write_upcoming(data_dir, merged, today)
        except Exception as exc:
            summary["errors"].append(f"upcoming: {type(exc).__name__}: {exc}")
    if check is None and collectors is COLLECTORS:
        check = watch.check
    if check is not None:
        try:
            missing = check(merged, today)
            summary["collectors"]["watch"] = {"ok": not missing, "fetched": 0, "added": 0}
            summary["errors"].extend(f"watch: {m}" for m in missing)
        except Exception as exc:
            summary["collectors"]["watch"] = {"ok": False, "fetched": 0, "added": 0}
            summary["errors"].append(f"watch: {type(exc).__name__}: {exc}")

    # 발표일 재수집(--due)은 몇 기관만 돈다. 나머지 기관의 그날 기록(오류 포함)을
    # 지우면 check_run 과 관리자 화면이 실패를 못 본다 — 돈 것만 갈아 끼운다.
    if partial and previous:
        ran = set(summary["collectors"])
        def others(entries):
            return [e for e in entries if e.split(":", 1)[0].strip() not in ran]
        summary["collectors"] = {**previous["collectors"], **summary["collectors"]}
        summary["errors"] = others(previous["errors"]) + summary["errors"]
        summary["warnings"] = others(previous.get("warnings", [])) + summary["warnings"]
        summary["blocked"] = {**{k: v for k, v in blocked_since.items() if k not in ran},
                              **summary["blocked"]}
        summary["conflicts"] = previous["conflicts"] + summary["conflicts"]

    if len(merged) != len(existing):
        store.save_forecasts(forecasts_path, merged)
    last_run_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary["collectors"], ensure_ascii=False))
    for warning in summary["warnings"]:
        print(f"경고: {warning}")
    return 0


def due_main(data_dir: Path = DATA_DIR, now: datetime | None = None) -> int:
    """발표 시각이 지난 기관만 다시 수집한다(작업 스케줄러가 매시간 부른다)."""
    now = now or datetime.now(KST)
    records = store.load_forecasts(data_dir / "forecasts.json")
    orgs = calendar.due(records, calendar.load_schedule(data_dir), now)
    if not orgs:
        print(f"{now:%H:%M} 지금 볼 기관 없음")
        return 0
    names = calendar.collectors_for(orgs)
    print(f"{now:%H:%M} 발표일 재수집: {', '.join(orgs)} ({', '.join(names)})")
    return main(data_dir, {name: COLLECTORS[name] for name in names}, partial=True)


if __name__ == "__main__":
    import sys
    raise SystemExit(due_main() if "--due" in sys.argv[1:] else main())
