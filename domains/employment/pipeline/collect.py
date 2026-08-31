"""고용동향 수집 오케스트레이터.

수집기 하나가 실패해도 나머지는 진행한다. 실패는 last_run.json 에 한 줄로
남긴다 — 이 파일은 저장소에 커밋되므로 트레이스백을 담으면 돌린 사람의
절대경로까지 함께 실린다.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from . import check_kosis, releases, store
from .collectors import eaps, ei, est
from .models import SeriesRecord

KST = timezone(timedelta(hours=9))
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

COLLECTORS: dict[str, Callable[[date], list[SeriesRecord]]] = {
    "eaps": eaps.collect,
    "est": est.collect,
    "ei": ei.collect,
}


def load_manual(data_dir: Path) -> list[SeriesRecord]:
    """수기 입력 폴백. 파싱이 깨진 달을 손으로 채울 수 있게 한다."""
    manual_dir = data_dir / "manual"
    if not manual_dir.is_dir():
        return []
    records: list[SeriesRecord] = []
    for path in sorted(manual_dir.glob("*.json")):
        rows = json.loads(path.read_text(encoding="utf-8"))
        records.extend(SeriesRecord.model_validate(row) for row in rows)
    return records


def _extras(name: str, index: dict, data_dir: Path) -> dict:
    """사업체노동력조사만 색인을 받는다. KOSIS 반영이 한 달 늦어서 아직 없는
    달을 보도자료에서 보충하는데, 그러려면 그 달 게시글과 첨부를 알아야 한다."""
    if name != "est" or not index:
        return {}
    try:
        rows = json.loads((data_dir / "industries.json").read_text(encoding="utf-8"))
    except Exception:
        return {}
    names = {re.sub(r"\s+", "", r["name_ko"]): r["code"] for r in rows}
    return {"releases_index": index, "industries": names}


def main(data_dir: Path = DATA_DIR,
         collectors: dict[str, Callable[[date], list[SeriesRecord]]] | None = None,
         *,
         refresh_releases: Callable | None = None,
         check_table: Callable | None = None,
         ) -> int:
    """수집 한 바퀴.

    refresh_releases·check_table 은 게시판과 KOSIS 를 두드리는 부분이라 주입할 수
    있게 열어 둔다. 기본값을 그대로 부르면 테스트가 매번 바깥 세상에 나간다 —
    collectors 를 주입하는 테스트는 네트워크를 쓰지 않겠다는 뜻이므로, 그 경우
    이 둘도 기본으로 끈다.
    """
    offline = collectors is not None
    collectors = COLLECTORS if collectors is None else collectors
    if refresh_releases is None:
        refresh_releases = (lambda existing: (existing, {})) if offline else releases.refresh
    if check_table is None:
        check_table = (lambda records: None) if offline else check_kosis.check
    series_path = data_dir / "series.json"
    last_run_path = data_dir / "last_run.json"
    today = datetime.now(KST).date()

    merged = store.load_series(series_path)
    index: dict = {}
    releases_path = data_dir / "releases.json"
    summary = {
        "run_at": datetime.now(KST).isoformat(),
        "collectors": {},
        "conflicts": [],
        "errors": [],
    }

    # 월별 보도자료 색인. 숫자가 아니라 출처를 담으므로 여기서 실패해도 그날 수집을
    # 망치지 않는다 — 한 줄 남기고 넘어가고, 화면은 아직 못 채운 달을 게시판 목록으로
    # 보낸다. 첫 실행은 상세를 MAX_DETAILS_PER_RUN 만큼만 채우고 며칠에 걸쳐 완성된다.
    try:
        existing_index = json.loads(releases_path.read_text(encoding="utf-8"))             if releases_path.exists() else {}
        index, index_summary = refresh_releases(existing_index)
        releases_path.write_text(
            json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + chr(10),
            encoding="utf-8")
        summary["releases"] = index_summary
    except Exception as exc:
        summary["errors"].append(f"releases: {type(exc).__name__}: {exc}")

    for name, collect_fn in collectors.items():
        try:
            candidates = collect_fn(today, **_extras(name, index, data_dir))
            result = store.upsert(merged, candidates)
            merged = result.records
            summary["collectors"][name] = {
                "ok": True, "fetched": len(candidates),
                "added": len(result.added), "updated": len(result.updated),
                "rejected": len(result.rejected),
            }
        except Exception as exc:
            summary["collectors"][name] = {
                "ok": False, "fetched": 0, "added": 0, "updated": 0, "rejected": 0,
            }
            summary["errors"].append(f"{name}: {type(exc).__name__}: {exc}")

    # KOSIS 표가 아직 보도자료와 같은 것을 말하는지 대조한다. 분류 개편으로 표
    # id 가 바뀌면 화면의 KOSIS 링크가 조용히 다른 표를 가리키게 된다 — 이 도메인이
    # 막으려는 종류의 사고라 시끄럽게 남긴다. 다만 대조를 '못 한' 것(키 없음·KOSIS
    # 장애)과 대조에 '실패한' 것은 다르므로, 앞은 메모로 뒤는 오류로 남긴다.
    try:
        note = check_table(merged)
        if note:
            summary["kosis_check"] = note
    except Exception as exc:
        summary["errors"].append(f"kosis_check: {type(exc).__name__}: {exc}")

    # 수기 입력은 마지막에 얹어 수집 결과를 이긴다.
    # 손으로 급히 채운 파일이 깨져 있어도 이미 수집한 세 결과를 버리지 않는다 —
    # 여기서 예외가 새면 series.json·last_run.json 이 통째로 안 쓰여, 어제자
    # 초록 결과가 오늘도 그대로 남아 실행이 있었는지조차 알 수 없게 된다.
    try:
        manual = load_manual(data_dir)
        if manual:
            merged = store.upsert(merged, manual).records
    except Exception as exc:
        summary["errors"].append(f"manual: {type(exc).__name__}: {exc}")

    store.save_series(series_path, merged)
    last_run_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary["collectors"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
