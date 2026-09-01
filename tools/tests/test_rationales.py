from datetime import date

import pytest

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


# ---------------------------------------------------------------------------
# 리뷰에서 지적된 critical/important 을 잡는 테스트들.
# ---------------------------------------------------------------------------


def test_refresh_does_not_delete_when_the_target_is_not_regenerated(tmp_path):
    """--only 로 다른 기관만 골랐는데 --refresh 로 KDI 를 지정한 경우.

    이번 실행은 KDI 소스를 아예 부르지 않으므로 대체물을 만들 수 없다.
    옛 구현은 refresh 대상을 먼저 지우고 나중에 채우는 순서라, 이 경우
    대체물 없이 지운 채로 끝났다(리뷰가 재현한 실제 버그: `--only bok
    --refresh KDI:...` → 사람이 고친 KDI 문장이 조용히 사라진다). 지금은
    실제로 새 근거를 만들었을 때만 지운다 — 그래서 KDI 항목이 그대로
    남아야 한다.
    """
    kdi_published_at = date(2026, 8, 19)
    rs.save(tmp_path / "rationales.json", [rs.Rationale(
        org="KDI", published_at=kdi_published_at, indicator="emp_change",
        text="사람이 고친 문장", tags=[], source_url="https://x/y.pdf", source_page=2)])

    def bok_listed():
        from domains.forecast.pipeline.documents import Listed
        return [Listed(org="BOK", title="b", published_at=date(2026, 8, 20),
                        indicators=("gdp_growth",),
                        fetch_pages=lambda: (
                            "https://bok/1.pdf",
                            ["", "성장률은 수출 호조에 힘입어 오를 것으로 전망된다."]))]

    def bok_select(*a, **k):
        from domains.forecast.pipeline.llm_select import Picked
        return [Picked("gdp_growth", "성장률은 수출 호조에 힘입어 오를 것으로 전망된다.", 2)]

    rep = rationales.run(
        tmp_path,
        sources={"bok": bok_listed, "kdi": lambda: [_listed()]},
        select=bok_select,
        only=["bok"],
        refresh={("KDI", kdi_published_at, "emp_change")})

    saved = rs.load(tmp_path / "rationales.json")
    kdi_saved = [r for r in saved if r.org == "KDI"]
    assert len(kdi_saved) == 1
    assert kdi_saved[0].text == "사람이 고친 문장"
    assert any("KDI" in line and "그대로 둔다" in line for line in rep.lines)


def test_refresh_target_with_no_matching_record_is_reported(tmp_path):
    # 기관·발표일·지표 표기가 하나라도 틀리면 이 키는 existing 의 어떤
    # 항목과도 안 맞는다 — 조용히 무시하지 않고 그 사실을 알린다.
    rep = rationales.run(
        tmp_path, sources={"kdi": lambda: [_listed()]},
        select=lambda *a, **k: _pick(),
        refresh={("KDI", date(1999, 1, 1), "emp_change")})
    assert any("일치하는 기존 항목이 없다" in line for line in rep.lines)


def test_load_error_stops_before_any_write(tmp_path):
    """guarantee 2: 못 읽는 파일에는 아무것도 쓰지 않는다."""
    path = tmp_path / "rationales.json"
    path.write_text("{이건 유효한 JSON 이 아니다", encoding="utf-8")
    before = path.read_bytes()

    rep = rationales.run(tmp_path, sources={"kdi": lambda: [_listed()]},
                         select=lambda *a, **k: _pick())

    assert rep.saved == 0
    assert any("읽지 못했다" in line for line in rep.failures)
    assert path.read_bytes() == before


def test_source_listing_failure_does_not_stop_other_sources(tmp_path):
    """listing() 자체(회차 목록 얻기)가 터지는 경우 — fetch_pages 가 아니라
    목록 단계에서 죽는 출처다. 이걸 감싸는 try/except 가 따로 있어야 한다.
    """
    def boom_listing():
        raise ValueError("목록을 못 가져왔다")

    rep = rationales.run(
        tmp_path,
        sources={"bad": boom_listing, "kdi": lambda: [_listed()]},
        select=lambda *a, **k: _pick())

    assert rep.saved == 1
    assert any("bad" in f and "목록" in f for f in rep.failures)


def test_only_skips_sources_not_listed(tmp_path):
    calls = []

    def bad():
        calls.append("bad 가 불렸다")
        return [_listed(org="BAD")]

    rep = rationales.run(
        tmp_path, sources={"bad": bad, "kdi": lambda: [_listed()]},
        select=lambda *a, **k: _pick(), only=["kdi"])

    assert calls == []  # only 에 없는 소스는 listing() 조차 부르지 않는다
    assert rep.saved == 1


def test_out_of_range_source_page_gets_its_own_message(tmp_path):
    """쪽번호가 범위를 벗어나면 "원문에 없다"(지어낸 문장 취급)가 아니라
    쪽번호 문제라고 밝혀야 한다 — 원인이 다르면 사람이 쫓는 가설도 달라진다.
    """
    from domains.forecast.pipeline.llm_select import Picked

    rep = rationales.run(
        tmp_path, sources={"kdi": lambda: [_listed()]},
        select=lambda *a, **k: [Picked(
            "emp_change", "취업자는 내수 회복이 반영되어 늘어날 것으로 전망된다.", 99)])

    assert rep.saved == 0
    assert any("범위를 벗어난다" in line for line in rep.rejected)
    assert not any("원문에 없다" in line for line in rep.rejected)


def test_parse_refresh_reads_org_date_indicator():
    assert rationales._parse_refresh("KDI:2026-08-19:emp_change") == (
        "KDI", date(2026, 8, 19), "emp_change")


def test_parse_refresh_rejects_bad_format():
    with pytest.raises(ValueError):
        rationales._parse_refresh("bad-format")


def test_parse_refresh_rejects_bad_date():
    with pytest.raises(ValueError):
        rationales._parse_refresh("KDI:not-a-date:emp_change")


def test_main_rejects_unknown_only_org(capsys):
    rc = rationales.main(["--only", "not-a-real-org"])
    assert rc == 1
    assert "모르는 기관" in capsys.readouterr().out


def test_main_rejects_malformed_refresh(capsys):
    rc = rationales.main(["--refresh", "bad-format"])
    assert rc == 1
    assert "형식이 아니다" in capsys.readouterr().out


def test_main_runs_end_to_end_with_patched_sources(tmp_path, monkeypatch):
    # main() 이 인자를 파싱해 run() 까지 제대로 잇는지 — 네트워크 없이
    # SOURCES 와 select 를 모두 갈아 끼운다.
    monkeypatch.setattr(rationales, "DATA_DIR", tmp_path)
    monkeypatch.setattr(rationales, "SOURCES", {"kdi": lambda: [_listed()]})
    monkeypatch.setattr(rationales.llm_select, "select", lambda *a, **k: _pick())

    rc = rationales.main([])

    assert rc == 0
    saved = rs.load(tmp_path / "rationales.json")
    assert len(saved) == 1
