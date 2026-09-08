from tools.d1_sync import build_sql, collect, flatten_releases, sql_literal


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


def test_flatten_releases_real_data_has_146_rows():
    # eaps 39 + ei 56 + est 51 = 146. 원본이 바뀌면 이 숫자가 알려준다.
    tables = collect("employment")
    assert len(tables["release"]) == 146


def test_catalog_hyp_indicator_drops_time_grain():
    # ontology.json 의 hyp_indicators 행에는 time_grain 이 있지만(pydantic 모델
    # 검정력 체크용) hyp_indicator 표에는 그 컬럼이 없다. 안 떨어뜨리면 D1 INSERT
    # 가 없는 컬럼을 참조해 죽는다.
    tables = collect("catalog")
    assert tables["hyp_indicator"], "hyp_indicator 행이 비어 있으면 안 된다"
    for row in tables["hyp_indicator"]:
        assert "time_grain" not in row
