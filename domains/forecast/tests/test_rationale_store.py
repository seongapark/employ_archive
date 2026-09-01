from datetime import date

from domains.forecast.pipeline import rationale_store as rs


def _item(indicator="emp_change", text="가", **kw):
    base = dict(org="KDI", published_at=date(2026, 8, 19), indicator=indicator,
                text=text, tags=[], source_url="https://x/y.pdf", source_page=5)
    base.update(kw)
    return rs.Rationale(**base)


def test_merge_adds_a_new_item():
    got = rs.merge([], [_item()])
    assert len(got) == 1


def test_merge_does_not_overwrite_an_existing_item():
    # 사람이 고친 문장을 다음 수집이 지우면 안 된다
    kept = _item(text="사람이 고친 문장")
    got = rs.merge([kept], [_item(text="수집기가 새로 뽑은 문장")])
    assert len(got) == 1
    assert got[0].text == "사람이 고친 문장"


def test_merge_keys_on_org_date_and_indicator():
    got = rs.merge([_item(indicator="emp_change")], [_item(indicator="cpi")])
    assert {r.indicator for r in got} == {"emp_change", "cpi"}


def test_merge_keeps_the_first_of_duplicate_keys_in_new():
    # 같은 보고서의 페이지를 따로 처리하면 new 안에 같은 키를 가진 두 문장이
    # 생길 수 있다 — 브리핑의 seen 이 컴프리헨션 안에서 자라지 않아 원래
    # 구현은 둘 다 넣었다. 먼저 온 것(보고서의 앞쪽 페이지)이 살아남아야 한다.
    first = _item(text="첫 페이지 문장")
    second = _item(text="둘째 페이지 문장")
    got = rs.merge([], [first, second])
    assert len(got) == 1
    assert got[0].text == "첫 페이지 문장"


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "rationales.json"
    rs.save(path, [_item(tags=["수출"])])
    got = rs.load(path)
    assert got[0].tags == ["수출"]
    assert got[0].published_at == date(2026, 8, 19)


def test_load_returns_empty_when_the_file_is_absent(tmp_path):
    assert rs.load(tmp_path / "none.json") == []
