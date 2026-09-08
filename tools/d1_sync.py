"""정본 JSON 을 D1 upsert SQL 로 옮긴다.

**이 모듈은 실행하지 않는다.** SQL 을 표준출력으로 낼 뿐이고, 워크플로가
`wrangler d1 execute --file` 로 밀어넣는다. 그래야 테스트가 네트워크에 안 나가고,
D1 이 죽어도 수집이 죽지 않는다(스펙 §4).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

KEYS = {
    "source_catalog": ["id"], "capability": ["source_id"], "capability_limit": ["id"],
    "source_conflict": ["id"], "phenomenon": ["id"], "hypothesis": ["id"],
    "indicator": ["id"], "hyp_indicator": ["hypothesis_id", "indicator_id"],
    "observation": ["id"], "forecast": ["id"], "release": ["id"],
    "forecast_rationale": ["org", "published_at", "indicator"],
}

# domains/ask/worker/migrations/0001_init.sql 의 CREATE TABLE 컬럼과 1:1 로 맞춘다.
# 정본 JSON 은 pydantic 모델 검증용으로 D1 표에 없는 필드를 더 들고 있을 수 있다
# (예: hyp_indicators 의 time_grain, forecasts.json 의 confidence·collected_at,
# series.json 의 attachments·collected_at). 여기서 표 컬럼으로만 잘라낸다 —
# 안 그러면 INSERT 가 없는 컬럼을 참조해 D1 에서 죽는다(스펙과 무관하게 실제로 재현됨).
COLUMNS = {
    "source_catalog": ["id", "name_ko", "agency", "grade", "axis", "method", "auth", "endpoint",
                        "rate_limit", "archived", "priority", "terms_of_use", "body_storable",
                        "evidence", "verified_at", "evidence_status"],
    "capability": ["source_id", "주제", "집단축", "지역입도", "시간입도", "기간_from", "기간_to",
                   "공표시차", "evidence", "verified_at", "evidence_status"],
    "capability_limit": ["id", "source_id", "유형", "axis", "category", "내용", "사유",
                          "evidence", "verified_at", "evidence_status"],
    "source_conflict": ["id", "source_a", "source_b", "차이유형", "설명", "비교가능",
                         "evidence", "verified_at", "evidence_status"],
    "phenomenon": ["id", "name_ko", "정의", "지역", "기간", "time_grain", "근거서술"],
    "hypothesis": ["id", "phenomenon_id", "name_ko", "서술", "대립가설", "missing_for_verdict",
                   "우회경로", "검정력_주석"],
    "indicator": ["id", "name_ko", "source_id", "정의", "모집단", "단위", "공표시차", "커버리지한계",
                  "data_status", "time_grain", "compare_basis", "series_key"],
    "hyp_indicator": ["hypothesis_id", "indicator_id", "role", "timing", "expected_sign",
                       "lead_lag", "falsifies"],
    "observation": ["id", "source", "series", "breakdown", "category", "period", "value", "unit",
                     "yoy", "status", "rse", "rse_flag", "released_at", "release_url"],
    "forecast": ["id", "org", "report_title", "published_at", "target_year", "target_period",
                 "indicator", "value", "unit", "prev_value", "revision", "source_url", "landing_url"],
    "forecast_rationale": ["org", "published_at", "indicator", "text", "tags", "source_url", "source_page"],
    "release": ["id", "source", "month", "title", "posted_at", "url", "attachments"],
}


def sql_literal(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (list, dict)):
        v = json.dumps(v, ensure_ascii=False)
    return "'" + str(v).replace("'", "''") + "'"


def build_sql(tables: dict[str, list[dict]]) -> str:
    out = ["PRAGMA foreign_keys=OFF;", "BEGIN TRANSACTION;"]
    for table, rows in tables.items():
        if not rows:
            continue
        key = KEYS[table]
        cols = list(rows[0])
        upd = ", ".join(f"{c}=excluded.{c}" for c in cols if c not in key)
        for r in rows:
            vals = ", ".join(sql_literal(r.get(c)) for c in cols)
            out.append(
                f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({vals}) "
                f"ON CONFLICT({', '.join(key)}) DO UPDATE SET {upd};")
    out += ["COMMIT;", "PRAGMA foreign_keys=ON;"]
    return "\n".join(out) + "\n"


def _load(p):
    return json.loads((REPO / p).read_text(encoding="utf-8"))


def flatten_releases(data: dict) -> list[dict]:
    """{출처: {월: {...}}} → release 표 행. 스펙 §3-2 의 컬럼 모양으로 맞춘다.

    domains/employment/data/releases.json 은 배열이 아니라 출처별로 중첩된
    dict 다. 그대로 넘기면 build_sql 의 rows[0] 이 dict 가 아니라 str 이 되어 죽는다.
    """
    rows = []
    for source, months in data.items():
        for month, r in months.items():
            rows.append({
                "id": f"{source}-{month}",
                "source": source,
                "month": month,
                "title": r.get("title"),
                "posted_at": r.get("posted_at"),  # 원본에 없으면 None
                "url": r.get("url"),
                "attachments": r.get("attachments", []),
            })
    return rows


def _project(table: str, rows: list[dict]) -> list[dict]:
    """rows 를 COLUMNS[table] 로만 잘라낸다. hyp_indicator 의 time_grain 을
    떨어뜨리는 것도 이 일반 메커니즘으로 처리된다 — 표에 없는 컬럼은 전부 그렇다.
    """
    cols = COLUMNS[table]
    return [{c: r.get(c) for c in cols} for r in rows]


def collect(target: str) -> dict[str, list[dict]]:
    if target == "catalog":
        cap = _load("domains/ask/data/capabilities.json")
        ont = _load("domains/ask/data/ontology.json")
        tables = {
            "source_catalog": _load("domains/ask/data/sources.json"),
            "capability": cap["capabilities"], "capability_limit": cap["limits"],
            "source_conflict": _load("domains/ask/data/conflicts.json"),
            "phenomenon": ont["phenomena"], "hypothesis": ont["hypotheses"],
            "indicator": ont["indicators"],
            "hyp_indicator": ont["hyp_indicators"],
        }
    elif target == "employment":
        tables = {"observation": _load("domains/employment/data/series.json"),
                  "release": flatten_releases(_load("domains/employment/data/releases.json"))}
    elif target == "forecast":
        tables = {"forecast": _load("domains/forecast/data/forecasts.json"),
                  "forecast_rationale": _load("domains/forecast/data/rationales.json")}
    else:
        raise SystemExit(f"모르는 대상: {target} (catalog|employment|forecast)")
    return {t: _project(t, rows) for t, rows in tables.items()}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        raise SystemExit("사용법: python -m tools.d1_sync <catalog|employment|forecast>")
    sys.stdout.write(build_sql(collect(argv[0])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
