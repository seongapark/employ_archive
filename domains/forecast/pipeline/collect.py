from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from . import http, rationale_store as rs, store
from .collectors import bok, imf, kdi, keis, kiet, kli, oecd
from .models import ForecastRecord
from .rationale_store import Rationale

KST = timezone(timedelta(hours=9))
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

COLLECTORS: dict[str, Callable[[date], list[ForecastRecord]]] = {
    "oecd": oecd.collect,
    "imf": imf.collect,
    "bok": bok.collect,
    "kdi": kdi.collect,
    "kli": kli.collect,
    "kiet": kiet.collect,
    "keis": keis.collect,
}


def _kdi_rationales(today: date) -> list[Rationale]:
    # kdi.collect() 와 같은 이유로 list_issues() 의 드롭다운 전체를 열지 않고
    # 최신 회차 본문 페이지 하나만 본다.
    page_html = http.get(kdi.LIST_URL).text
    issue = kdi.parse_issue(page_html, kdi.LIST_URL)
    return kdi.collect_issue_rationales(issue, page_html)


# imf·oecd 는 없다 — 숫자를 API 로 읽어 근거로 삼을 본문이 없다. main() 은
# collectors 에 있는 이름이라도 여기 없으면 그냥 건너뛴다(부재를 견딘다).
RATIONALE_COLLECTORS: dict[str, Callable[[date], list[Rationale]]] = {
    "bok": lambda today: bok.collect_issue_rationales(bok.list_issues()[0]),
    "kdi": _kdi_rationales,
    "kli": lambda today: kli.collect_issue_rationales(kli.list_issues()[0]),
    "kiet": lambda today: kiet.collect_issue_rationales(kiet.list_issues()[0]),
    "keis": lambda today: keis.collect_issue_rationales(keis.list_issues()[0]),
}


def main(data_dir: Path = DATA_DIR,
         collectors: dict[str, Callable[[date], list[ForecastRecord]]] = COLLECTORS,
         rationale_collectors: dict[str, Callable[[date], list[Rationale]]] | None = None,
         ) -> int:
    # 기본값을 빈 dict 로 둔다 — collectors 처럼 실제 레지스트리를 기본값으로
    # 하면, collectors 만 바꿔 끼우는 기존 테스트들이 이름이 겹치는 순간
    # (예: "kdi") 모르게 네트워크를 타 버린다. 실제 운영은 __main__ 에서
    # RATIONALE_COLLECTORS 를 명시적으로 넘긴다.
    rationale_collectors = {} if rationale_collectors is None else rationale_collectors

    forecasts_path = data_dir / "forecasts.json"
    rationales_path = data_dir / "rationales.json"
    last_run_path = data_dir / "last_run.json"
    today = datetime.now(KST).date()

    existing = store.load_forecasts(forecasts_path)
    merged = existing
    existing_rationales = rs.load(rationales_path)
    merged_rationales = existing_rationales
    summary = {
        "run_at": datetime.now(KST).isoformat(),
        "collectors": {},
        "conflicts": [],
        "errors": [],
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
        except Exception as exc:
            # last_run.json 은 저장소에 커밋된다 — 트레이스백을 담으면 돌린 사람의
            # 절대경로까지 함께 실린다. 무엇이 왜 실패했는지만 한 줄로 남긴다.
            summary["collectors"][name] = {"ok": False, "fetched": 0, "added": 0}
            summary["errors"].append(f"{name}: {type(exc).__name__}: {exc}")

        # 근거 추출은 수치와 독립이다. 수치가 본체이므로, 근거 추출이 터져도
        # 위에서 이미 정한 summary["collectors"][name]["ok"] 는 건드리지 않는다
        # — 이 수집기의 수치 수집은 그것대로 성공이다.
        rationale_fn = rationale_collectors.get(name)
        if rationale_fn is None:
            continue
        try:
            rationale_candidates = rationale_fn(today)
        except Exception as exc:
            # name: 을 그대로 앞에 둬 check_run.py 의 KNOWN_DOWN 판정(콜론 앞
            # 토큰으로 수집기를 식별)이 수치 쪽과 같은 유예를 그대로 쓰게 한다.
            summary["errors"].append(f"{name}: 근거 {type(exc).__name__}: {exc}")
            continue
        merged_rationales = rs.merge(merged_rationales, rationale_candidates)

    if len(merged) != len(existing):
        store.save_forecasts(forecasts_path, merged)
    # 개수가 아니라 내용으로 비교한다 — merge 가 잘못 짜여 있는 값을 덮어써도
    # 개수는 그대로일 수 있는데(같은 키, 다른 문장), 개수만 보면 그 사고를
    # 놓치고 저장하지 않아 파일이 우연히 이전 그대로인 것처럼 보인다.
    if merged_rationales != existing_rationales:
        rs.save(rationales_path, merged_rationales)
    last_run_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary["collectors"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(rationale_collectors=RATIONALE_COLLECTORS))
