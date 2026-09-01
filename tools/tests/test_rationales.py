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
    assert any("KDI:2026-08-19:emp_change" in line and "그대로 둔다" in line
               for line in rep.lines)
    # 이 키는 존재하고(사람이 고친 항목이 있다) 이번 실행이 다시 만들지
    # 못했을 뿐이다 — 오타가 아니므로 unmatched_refresh 에는 안 들어간다
    # (exit code 판정에 영향을 주면 안 된다, coordinator 의 판단).
    assert rep.unmatched_refresh == []


def test_refresh_target_with_no_matching_record_is_reported(tmp_path):
    # 기관·발표일·지표 표기가 하나라도 틀리면 이 키는 existing 의 어떤
    # 항목과도 안 맞는다 — 조용히 무시하지 않고 그 사실을 알린다.
    bad_key = ("KDI", date(1999, 1, 1), "emp_change")
    rep = rationales.run(
        tmp_path, sources={"kdi": lambda: [_listed()]},
        select=lambda *a, **k: _pick(),
        refresh={bad_key})
    assert any("일치하는 기존 항목이 없다" in line for line in rep.lines)
    # 사람이 대조할 수 있게 파이썬 튜플이 아니라 입력한 형식 그대로 찍는다.
    assert any("KDI:1999-01-01:emp_change" in line for line in rep.lines)
    assert not any("datetime.date" in line for line in rep.lines)
    # main() 이 문자열을 뒤지지 않고 종료 코드를 정할 수 있도록 구조화된
    # 필드에도 남긴다.
    assert rep.unmatched_refresh == [bad_key]


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
    assert "모르는 소스키" in capsys.readouterr().out


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


# ---------------------------------------------------------------------------
# 2차 리뷰: main() 이 --only·--refresh 를 실제로 run() 에 넘기는지, 종료
# 코드가 rep.failures/rep.unmatched_refresh 를 실제로 보는지는 이전까지
# `main([])`(인자 없음, 실패 없음) 하나로만 확인했다 — 두 플래그도, 실패
# 경로도 전혀 자극하지 못했다. run() 을 흉내낸 스텁으로 main() 의 배선만
# 따로 확인한다.
# ---------------------------------------------------------------------------


def test_main_forwards_only_and_refresh_to_run(monkeypatch):
    captured = {}

    def fake_run(data_dir, *, sources=None, select=None, only=None, refresh=()):
        captured["only"] = only
        captured["refresh"] = refresh
        return rationales.Report()

    monkeypatch.setattr(rationales, "run", fake_run)

    rc = rationales.main(["--only", "kdi", "--refresh", "KDI:2026-08-19:emp_change"])

    assert rc == 0
    # --only 가 run() 까지 안 이어지면 SOURCES 에 있는 소스를 전부(=네트워크
    # 전부) 부르게 된다 — captured["only"] 가 None 이면 그 사고를 놓친다.
    assert captured["only"] == ["kdi"]
    # --refresh 가 안 이어지면 명령이 조용한 완전 무동작이 된다.
    assert captured["refresh"] == {("KDI", date(2026, 8, 19), "emp_change")}


def test_main_returns_1_when_run_reports_failures(monkeypatch):
    monkeypatch.setattr(
        rationales, "run",
        lambda *a, **k: rationales.Report(failures=["뭔가 실패했다"]))

    rc = rationales.main([])

    assert rc == 1


def test_main_returns_0_when_only_rejections_are_present(monkeypatch):
    # coordinator 의 판단: 거절만 있는 실행은 실패가 아니다 — 검증이
    # 설계대로 작동했을 뿐 아무것도 잃지 않았다.
    monkeypatch.setattr(
        rationales, "run",
        lambda *a, **k: rationales.Report(rejected=["원문에 없다고 거절됐다"]))

    rc = rationales.main([])

    assert rc == 0


def test_main_returns_1_when_a_refresh_target_matches_nothing(monkeypatch):
    # coordinator 의 판단: existing 의 어떤 키와도 안 맞는 refresh 대상은
    # 오타이므로 exit code 로 드러나야 한다 — 실행 로그 맨 아래 한 줄에
    # 묻히면 안 된다.
    monkeypatch.setattr(
        rationales, "run",
        lambda *a, **k: rationales.Report(
            unmatched_refresh=[("KDI", date(1999, 1, 1), "emp_change")]))

    rc = rationales.main([])

    assert rc == 1


def test_main_returns_0_when_refresh_target_exists_but_is_not_replaced(monkeypatch):
    # coordinator 의 판단: 대상은 실재하는데 이번 실행이 다시 못 만든 것은
    # 실패가 아니다 — 잃은 것이 없고 다시 돌리면 되는 정상적인 다음 수순이다.
    monkeypatch.setattr(
        rationales, "run",
        lambda *a, **k: rationales.Report(
            lines=["refresh KDI:2026-08-19:emp_change: 이번 실행에서 대체물을 "
                   "못 만들어 기존 항목을 그대로 둔다"]))

    rc = rationales.main([])

    assert rc == 0


def test_saved_count_reflects_a_refresh_replacement(tmp_path):
    """rep.saved 는 refresh 로 뺀 뒤의 집합(kept) 을 기준으로 세야 한다.

    existing 을 기준으로 세면(1차 리뷰의 critical 을 감춘 바로 그 계산)
    실제 교체가 일어났는데도 saved 가 0으로 나온다 — 이 계산 하나가
    critical 을 산술적으로 안 보이게 만든 원흉이라 별도로 못박는다.
    """
    published_at = date(2026, 8, 19)
    rs.save(tmp_path / "rationales.json", [rs.Rationale(
        org="KDI", published_at=published_at, indicator="emp_change",
        text="옛 문장", tags=[], source_url="https://x/y.pdf", source_page=2)])

    rep = rationales.run(
        tmp_path, sources={"kdi": lambda: [_listed()]},
        select=lambda *a, **k: _pick(),
        refresh={("KDI", published_at, "emp_change")})

    assert rep.saved == 1
    saved = rs.load(tmp_path / "rationales.json")
    assert len(saved) == 1
    assert saved[0].text == "취업자는 내수 회복이 반영되어 늘어날 것으로 전망된다."


def test_per_issue_line_reports_picked_stored_and_rejected_counts(tmp_path):
    rep = rationales.run(tmp_path, sources={"kdi": lambda: [_listed()]},
                         select=lambda *a, **k: _pick())
    assert any("후보 1건" in line and "저장 1건" in line and "거절 0건" in line
               for line in rep.lines)
