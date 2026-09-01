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

    # forecasts.json 은 기계만 쓰는 파일이라 못 읽으면 그건 진짜 사고다 —
    # 여기서 감싸지 않는다(rationale_store.load_or_empty 문서주석 참고).
    existing = store.load_forecasts(forecasts_path)
    merged = existing
    existing_rationales, rationale_load_error = rs.load_or_empty(rationales_path)
    merged_rationales = existing_rationales
    summary = {
        "run_at": datetime.now(KST).isoformat(),
        "collectors": {},
        "conflicts": [],
        "errors": [],
        # 근거 실패는 수치 실패와 **다른 칸**에 넣는다. 예전엔 둘 다
        # errors 에 섞였는데, check_run.py 가 errors 를 첫 콜론으로 잘라
        # 수집기 이름을 얻으므로 "keis: 근거 ValueError: …" 가 keis 의
        # 수치 장애로 둔갑했다. KNOWN_DOWN 으로 유예를 주면 이번엔
        # check_run 의 두 번째 루프가 "collectors['keis'].ok 가 True 인데
        # 유예 목록에 있다" 며 실패시킨다 — 근거가 죽고 수치가 산 날은
        # 두 갈래 어디로 가도 빨갛고, 안내문은 다시 첫 갈래로 보낸다.
        # 칸을 나누면 그 고리 자체가 사라진다.
        "rationale_errors": [],
    }
    if rationale_load_error is not None:
        summary["rationale_errors"].append(
            f"rationales.json 을 읽지 못해 이번 실행은 근거를 비운 채로 "
            f"진행한다(저장도 건너뛴다) — {rationale_load_error}")

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
            # "{name}: " 접두는 어느 기관의 근거가 죽었는지 읽으라고 남긴다 —
            # KNOWN_DOWN 판정에는 더 이상 쓰이지 않는다(위 rationale_errors
            # 주석 참고).
            summary["rationale_errors"].append(
                f"{name}: 근거 {type(exc).__name__}: {exc}")
            continue
        merged_rationales = rs.merge(merged_rationales, rationale_candidates)

    if len(merged) != len(existing):
        store.save_forecasts(forecasts_path, merged)
    # 개수가 아니라 내용으로 비교한다 — merge 가 잘못 짜여 있는 값을 덮어써도
    # 개수는 그대로일 수 있는데(같은 키, 다른 문장), 개수만 보면 그 사고를
    # 놓치고 저장하지 않아 파일이 우연히 이전 그대로인 것처럼 보인다.
    #
    # 못 읽은 파일에는 쓰지 않는다 — 사람이 고치던 편집물을 우리가 지우게
    # 된다(rationale_store.load_or_empty 문서주석).
    if rationale_load_error is None and merged_rationales != existing_rationales:
        rs.save(rationales_path, merged_rationales)
    last_run_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary["collectors"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(rationale_collectors=RATIONALE_COLLECTORS))
