from datetime import date

from domains.forecast.pipeline import rationale_store as rs
from tools import rationales


PAGES = ["", "취업자는 내수 회복이 반영되어 늘어날 것으로 전망된다."]


def _listed(**kw):
    base = dict(org="KDI", title="t", published_at=date(2026, 8, 19),
                indicators=("emp_change",),
                fetch_pages=lambda: ("https://x/y.pdf", PAGES))
    base.update(kw)
    from domains.forecast.pipeline.documents import Listed
    return Listed(**base)


def _pick(text="취업자는 내수 회복이 반영되어 늘어날 것으로 전망된다.", page=2):
    from domains.forecast.pipeline.llm_select import Picked
    return [Picked("emp_change", text, page)]


def test_saves_a_verified_rationale(tmp_path):
    rep = rationales.run(tmp_path, sources={"kdi": lambda: [_listed()]},
                         select=lambda *a, **k: _pick())
    assert rep.saved == 1
    saved = rs.load(tmp_path / "rationales.json")
    assert saved[0].indicator == "emp_change"
    assert saved[0].source_page == 2
    assert saved[0].tags == ["내수"]


def test_drops_a_candidate_that_is_not_in_the_source(tmp_path):
    rep = rationales.run(tmp_path, sources={"kdi": lambda: [_listed()]},
                         select=lambda *a, **k: _pick(text="지어낸 문장이다."))
    assert rep.saved == 0
    assert any("원문에 없다" in line for line in rep.rejected)
    assert rs.load(tmp_path / "rationales.json") == []


def test_does_not_overwrite_a_human_edited_sentence(tmp_path):
    rs.save(tmp_path / "rationales.json", [rs.Rationale(
        org="KDI", published_at=date(2026, 8, 19), indicator="emp_change",
        text="사람이 고친 문장", tags=[], source_url="https://x/y.pdf", source_page=2)])
    rationales.run(tmp_path, sources={"kdi": lambda: [_listed()]},
                   select=lambda *a, **k: _pick())
    assert rs.load(tmp_path / "rationales.json")[0].text == "사람이 고친 문장"


def test_one_failing_source_does_not_stop_the_others(tmp_path):
    def boom():
        raise ValueError("본문을 못 받았다")

    rep = rationales.run(
        tmp_path,
        sources={"bad": lambda: [_listed(fetch_pages=boom)], "kdi": lambda: [_listed()]},
        select=lambda *a, **k: _pick())
    assert rep.saved == 1
    assert len(rep.failures) == 1


def test_never_writes_forecasts_json(tmp_path):
    (tmp_path / "forecasts.json").write_text("[]", encoding="utf-8")
    before = (tmp_path / "forecasts.json").read_bytes()
    rationales.run(tmp_path, sources={"kdi": lambda: [_listed()]},
                   select=lambda *a, **k: _pick())
    assert (tmp_path / "forecasts.json").read_bytes() == before


def test_drops_a_candidate_for_an_indicator_the_institution_does_not_forecast(tmp_path):
    # KDI 가 emp_change 만 전망하는데 모델이 gdp_growth 문장을 돌려주는 경우 —
    # p.indicator not in listed.indicators 검사만 자극한다. 후보 문장 자체는
    # 원문에 실재하므로(PAGES[1]) llm_verify.verify 는 통과할 것이다 — 이
    # 테스트가 실패로 잡아야 하는 건 오직 지표 대조 하나뿐이다.
    from domains.forecast.pipeline.llm_select import Picked

    rep = rationales.run(
        tmp_path, sources={"kdi": lambda: [_listed(indicators=("emp_change",))]},
        select=lambda *a, **k: [Picked(
            "gdp_growth", "취업자는 내수 회복이 반영되어 늘어날 것으로 전망된다.", 2)])

    assert rep.saved == 0
    assert any("전망하지 않는 지표" in line for line in rep.rejected)
    assert rs.load(tmp_path / "rationales.json") == []
