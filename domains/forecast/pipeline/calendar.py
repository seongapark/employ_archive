"""발표가 날 만한 날·시각에 그 기관만 다시 수집한다.

매일 수집은 11:00 한 번이다. 그런데 OECD 는 17시, IMF 는 22시에 낸다 — 11시
수집은 그날 발표를 원리적으로 못 받고 다음 날에야 반영된다. 그래서 발표일
언저리에는 발표 시각 이후에 그 기관만 다시 본다(`collect --due`, 작업
스케줄러가 10~23시 매시간 부른다).

발표일은 두 곳에서 온다.
1. `schedule.json` — 기관이 미리 공지한 날(한국은행 금통위 일정, OECD 보도 안내 등).
   그날은 발표 시각부터 매시간 본다.
2. 지난 발표일 — 최근 24개월 안에 발표가 있었던 달마다, 그 달의 발표일
   최소~최대에 앞뒤 PAD_DAYS 를 붙인 구간을 올해의 예상 구간으로 본다.
   날짜가 확정이 아니므로 3시간마다만 본다(게시판 예의).
새 회차가 이미 들어와 있으면(최신 발표일 ≥ 구간 시작) 더 보지 않는다.
KEIS 처럼 한 달에 한 번뿐인 불규칙 기관도 구간이 생기지만, 빗나가도 매일
수집과 감시(watch)가 남아 있다.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from .models import ForecastRecord

KST = timezone(timedelta(hours=9))
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# 발표 시각(KST, 시). OECD·IMF 는 원문으로 실측했다 — OECD 는 발간 페이지
# datePublished 08:00Z·보도 안내 "10:00 CEST", IMF 는 WEO 데이터셋
# PUBLICATION_DATE 13:00Z. 둘 다 서머타임이 끝나면 한 시간 늦어지는데, 발표
# 다음 시각에도 한 번 더 보므로 따로 다루지 않는다. 국내 기관은 추정이다.
RELEASE_HOUR = {"OECD": 17, "IMF": 22, "KDI": 12}
DEFAULT_RELEASE_HOUR = 10

PAD_DAYS = 3
LOOKBACK_DAYS = 730
WINDOW_EVERY_HOURS = 3

# 기관 → 매일 수집(collect.COLLECTORS)의 이름들
_COLLECTORS = {"OECD": ["oecd", "oecd_interim"], "IMF": ["imf", "imf_update"]}


def collectors_for(orgs: Iterable[str]) -> list[str]:
    return [name for org in orgs for name in _COLLECTORS.get(org, [org.lower()])]


def _release_days(records: list[ForecastRecord], org: str) -> list[date]:
    return sorted({r.published_at for r in records if r.org == org})


def next_window(records: list[ForecastRecord], org: str, today: date) -> tuple[date, date] | None:
    """아직 안 들어온 가장 이른 예상 구간(시작, 끝). 끝이 오늘 이전인 구간은 뺀다."""
    days = _release_days(records, org)
    if not days:
        return None
    latest = days[-1]
    by_month: dict[int, list[int]] = {}
    for d in days:
        if (today - d).days <= LOOKBACK_DAYS:
            by_month.setdefault(d.month, []).append(d.day)

    windows = []
    for month, month_days in by_month.items():
        for year in (today.year - 1, today.year, today.year + 1):
            start = date(year, month, min(month_days)) - timedelta(days=PAD_DAYS)
            end = date(year, month, max(month_days)) + timedelta(days=PAD_DAYS)
            if end >= today and start > latest:
                windows.append((start, end))
    return min(windows) if windows else None


def _hours(release_hour: int, every: int) -> set[int]:
    # 발표 시각, 그 다음 시각(서머타임·게시 지연), 그 뒤로는 every 시간마다
    return {h for h in range(release_hour, 24)
            if (h - release_hour) % every == 0 or h == release_hour + 1}


def due(records: list[ForecastRecord], schedule: list[dict], now: datetime) -> list[str]:
    """지금 다시 수집할 기관들."""
    today = now.astimezone(KST).date()
    hour = now.astimezone(KST).hour
    orgs = sorted({r.org for r in records} | {s["org"] for s in schedule})
    out = []
    for org in orgs:
        release_hour = RELEASE_HOUR.get(org, DEFAULT_RELEASE_HOUR)
        days = _release_days(records, org)
        latest = days[-1] if days else date.min

        announced = [date.fromisoformat(s["date"]) for s in schedule if s["org"] == org]
        if any(d <= today <= d + timedelta(days=PAD_DAYS) and latest < d for d in announced):
            if hour in _hours(release_hour, 1):
                out.append(org)
            continue

        window = next_window(records, org, today)
        if window and window[0] <= today <= window[1] and hour in _hours(release_hour, WINDOW_EVERY_HOURS):
            out.append(org)
    return out


def load_schedule(data_dir: Path = DATA_DIR) -> list[dict]:
    path = Path(data_dir) / "schedule.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def main(argv: list[str] | None = None) -> int:
    """오늘부터 기관별 다음 예상 구간을 보여 준다(사람이 확인하는 용도)."""
    from . import store

    parser = argparse.ArgumentParser()
    parser.add_argument("--today", type=date.fromisoformat, default=datetime.now(KST).date())
    args = parser.parse_args(argv)
    records = store.load_forecasts(DATA_DIR / "forecasts.json")
    schedule = load_schedule()
    for org in sorted({r.org for r in records}):
        announced = [s["date"] for s in schedule if s["org"] == org and s["date"] >= args.today.isoformat()]
        window = next_window(records, org, args.today)
        hour = RELEASE_HOUR.get(org, DEFAULT_RELEASE_HOUR)
        span = f"{window[0]}~{window[1]}" if window else "없음"
        print(f"{org:5} 공지 {','.join(announced) or '-':12} 예상 {span:22} {hour}시부터")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
