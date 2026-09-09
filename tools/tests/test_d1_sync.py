import json
import re
from pathlib import Path

from tools.d1_sync import REPO, COLUMNS, KEYS, build_sql, collect, flatten_releases, sql_literal

MIGRATION = (Path(__file__).resolve().parents[2]
             / "domains/ask/worker/migrations/0001_init.sql")


def test_string_literal_escapes_single_quote():
    assert sql_literal("O'Brien") == "'O''Brien'"


def test_none_becomes_null_and_bool_becomes_int():
    assert sql_literal(None) == "NULL"
    assert sql_literal(True) == "1"
    assert sql_literal(False) == "0"


def test_list_is_stored_as_json_text():
    # D1 은 SQLite 라 배열 타입이 없다. JSON 문자열로 담고 읽을 때 파싱한다
    assert sql_literal(["산업", "성"]) == "'[\"산업\", \"성\"]'"


def test_upsert_is_idempotent_on_primary_key():
    sql = build_sql({"source_catalog": [{"id": "eaps", "name_ko": "경활", "grade": "B"}]})
    assert "INSERT INTO source_catalog" in sql
    assert "ON CONFLICT(id) DO UPDATE SET" in sql
    assert 'name_ko=excluded.name_ko' in sql
    assert 'id=excluded.id' not in sql   # 키 자신은 갱신하지 않는다


def test_composite_key_table_uses_both_columns():
    sql = build_sql({"hyp_indicator": [
        {"hypothesis_id": "H1", "indicator_id": "I1", "role": "지지", "timing": "특정성"}]})
    assert "ON CONFLICT(hypothesis_id, indicator_id) DO UPDATE SET" in sql


def test_generation_does_not_execute_anything(monkeypatch):
    # 이 모듈은 SQL 을 만들기만 한다. 실행은 워크플로가 wrangler 로 한다
    import tools.d1_sync as m
    assert not hasattr(m, "requests")
    assert "subprocess" not in dir(m)


def test_flatten_releases_unnests_source_month_dict():
    # domains/employment/data/releases.json 은 배열이 아니라
    # {출처: {월: {...}}} 로 중첩된 dict 다. 펼쳐야 release 표에 들어간다.
    data = {
        "eaps": {"2023-05": {"title": "t1", "url": "u1", "attachments": [{"type": "pdf"}]}},
        "ei": {"2022-01": {"title": "t2", "posted_at": "2022-02-14", "url": "u2"}},
    }
    rows = flatten_releases(data)
    assert len(rows) == 2
    row = next(r for r in rows if r["source"] == "eaps")
    assert row["id"] == "eaps-2023-05"
    assert row["month"] == "2023-05"
    assert row["title"] == "t1"
    assert row["posted_at"] is None   # 원본에 없으면 None
    assert row["attachments"] == [{"type": "pdf"}]
    row2 = next(r for r in rows if r["source"] == "ei")
    assert row2["posted_at"] == "2022-02-14"


def test_flatten_releases_loses_no_rows():
    """중첩 dict 를 펼치면서 행이 새거나 겹치지 않는지 본다.

    처음에는 146 이라는 숫자를 박아 뒀는데, 매일 도는 수집이 회차를 하나 늘리자
    바로 빨개졌다. 지키려던 것은 그 숫자가 아니라 **펼치면서 아무것도 잃지 않는다**
    는 불변이므로, 원본에서 직접 세어 대조한다. 회차가 늘어도 안 깨지고,
    행이 사라지거나 겹치면 깨진다.
    """
    src = json.loads((REPO / "domains/employment/data/releases.json")
                     .read_text(encoding="utf-8"))
    기대 = sum(len(months) for months in src.values())
    rows = collect("employment")["release"]
    assert len(rows) == 기대
    # id 가 유일해야 upsert 가 회차를 덮어쓰지 않는다
    assert len({r["id"] for r in rows}) == 기대
    # 출처별로도 어긋나지 않는다
    for source, months in src.items():
        assert sum(1 for r in rows if r["source"] == source) == len(months), source


def test_catalog_hyp_indicator_drops_time_grain():
    # ontology.json 의 hyp_indicators 행에는 time_grain 이 있지만(pydantic 모델
    # 검정력 체크용) hyp_indicator 표에는 그 컬럼이 없다. 안 떨어뜨리면 D1 INSERT
    # 가 없는 컬럼을 참조해 죽는다.
    tables = collect("catalog")
    assert tables["hyp_indicator"], "hyp_indicator 행이 비어 있으면 안 된다"
    for row in tables["hyp_indicator"]:
        assert "time_grain" not in row


def _split_top_level(body: str) -> list[str]:
    """CREATE TABLE 본문을 괄호 깊이 0 인 콤마 기준으로만 쪼갠다.

    CHECK(... , ...) 나 IN (...) 안의 콤마를 컬럼 구분자로 착각하지 않기 위함.
    """
    parts, depth, cur = [], 0, []
    for ch in body:
        if ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


def schema_columns() -> dict[str, list[str]]:
    """0001_init.sql 에서 표별 컬럼명을 실측한다. COLUMNS 를 손으로 맞추지 않게 하는 것이 목적.

    줄 주석(`-- ...`)을 먼저 지운다 — 안 그러면 콤마 뒤에 붙은 줄 주석이 다음 줄의
    컬럼까지 "주석 세그먼트"로 삼켜서 컬럼 하나가 조용히 사라진다(hypothesis 표의
    `missing_for_verdict` 에서 실제로 재현됨: `대립가설 ... ),   -- §8 ...` 다음 줄의
    `missing_for_verdict TEXT` 가 콤마로 안 끊기고 주석과 한 세그먼트로 묶여 통째로
    스킵됐었다). 주석 제거를 빼먹으면 이 테스트가 "통과"는 하되 아무것도 안 잡는
    가장 위험한 실패로 이어지므로, 아래 표 개수 단언으로 그 경우를 막는다.
    """
    sql = re.sub(r"--[^\n]*", "", MIGRATION.read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {}
    for m in re.finditer(r"CREATE TABLE (\w+)\s*\((.*?)\n\);", sql, re.S):
        table, body = m.group(1), m.group(2)
        cols = []
        for part in _split_top_level(body):
            part = part.strip()
            if not part or part.startswith(("PRIMARY KEY", "CHECK", "FOREIGN KEY", "UNIQUE")):
                continue
            cols.append(part.split()[0])
        out[table] = cols
    return out


def test_schema_parser_finds_all_twelve_tables():
    # 파싱이 표를 못 잡으면 아래 컬럼 일치 테스트가 조용히 통과해버린다(가장 위험한
    # 실패 방식). 표 개수를 먼저 못박아 그 경우를 막는다.
    schema = schema_columns()
    assert len(schema) == 12
    assert set(schema) == set(COLUMNS)


def test_columns_match_the_migration_exactly():
    # COLUMNS 가 0001_init.sql 과 어긋나면(컬럼이 조용히 빠지든, 스키마에 컬럼이
    # 생겼는데 COLUMNS 에 안 들어오든) build_sql 이 없는 컬럼을 INSERT 하거나
    # 있어야 할 컬럼을 빠뜨려 D1 에서 죽는다. 12표 전부를 실측 스키마와 대조한다.
    schema = schema_columns()
    for table, cols in schema.items():
        assert COLUMNS[table] == cols, table


def test_keys_are_real_primary_keys():
    # KEYS 가 가리키는 컬럼이 실제로 그 표에 존재하는지 확인한다.
    schema = schema_columns()
    for table, key in KEYS.items():
        for k in key:
            assert k in schema[table], (table, k)


def test_no_transaction_statements():
    """D1 원격 실행이 BEGIN/COMMIT 을 거부한다 — 로컬 sqlite3 는 받아 줘서 배포에서야 드러났다."""
    sql = build_sql({"source_catalog": [{"id": "eaps", "name_ko": "경활", "grade": "B"}]})
    upper = sql.upper()
    assert "BEGIN TRANSACTION" not in upper
    assert "COMMIT" not in upper
    assert "PRAGMA" not in upper
