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


def test_merge_keys_on_org():
    # org 만 다르면 같은 (날짜, 지표) 라도 서로 다른 항목이다 — KDI 와 BOK 의
    # 근거를 한 줄로 합치면 안 된다.
    got = rs.merge([_item(org="KDI")], [_item(org="BOK")])
    assert {r.org for r in got} == {"KDI", "BOK"}


def test_merge_keys_on_published_at():
    # 발표일만 달라도 서로 다른 항목이다 — 같은 기관의 두 발표를 하나로
    # 합치면 안 된다.
    got = rs.merge([_item(published_at=date(2026, 8, 19))],
                   [_item(published_at=date(2026, 9, 19))])
    assert {r.published_at for r in got} == {date(2026, 8, 19), date(2026, 9, 19)}


def test_merge_keys_on_indicator():
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


def test_merge_does_not_mutate_its_inputs():
    # 호출자가 existing 리스트를 수집 루프에서 재사용할 수 있다(Task 6) —
    # merge 가 그 리스트를 제자리에서 바꾸면 다음 반복이 오염된다.
    existing = [_item(indicator="emp_change")]
    new = [_item(indicator="cpi")]
    existing_before = list(existing)
    new_before = list(new)
    rs.merge(existing, new)
    assert existing == existing_before
    assert new == new_before


def test_save_and_load_round_trip(tmp_path):
    # source_page=None 을 쓴다 — 쪽수가 없는 보고서에서 Task 4 가 실제로
    # 넘길 값이고, source_page 는 default_factory 가 아니라 단순 기본값을
    # 가진 유일한 필드라 None 이 왕복하는지 따로 확인할 필요가 있다.
    path = tmp_path / "rationales.json"
    rs.save(path, [_item(tags=["수출"], source_url="https://x/y.pdf", source_page=None)])
    got = rs.load(path)
    assert got[0].tags == ["수출"]
    assert got[0].published_at == date(2026, 8, 19)
    assert got[0].source_url == "https://x/y.pdf"
    assert got[0].source_page is None


def test_load_returns_empty_when_the_file_is_absent(tmp_path):
    assert rs.load(tmp_path / "none.json") == []
