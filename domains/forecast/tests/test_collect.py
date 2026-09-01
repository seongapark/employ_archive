import json
from datetime import date, datetime

import pytest

from domains.forecast.pipeline.models import ForecastRecord, make_id
from domains.forecast.pipeline import collect, store
from domains.forecast.pipeline import rationale_store as rs


def fake_record(value: float, pub: date) -> ForecastRecord:
    return ForecastRecord(
        id=make_id("OECD", pub, "gdp_growth", 2027), org="OECD", org_name_ko="OECD",
        report_title="test", published_at=pub, target_year=2027,
        indicator="gdp_growth", value=value, unit="%",
        source_url="https://example.com/a", landing_url="https://example.com",
        confidence="verified", collected_at=datetime(2026, 8, 29, 16, 0),
    )


def test_main_saves_new_records_and_last_run(tmp_path):
    collectors = {"fake": lambda today: [fake_record(2.0, today)]}
    rc = collect.main(data_dir=tmp_path, collectors=collectors)
    assert rc == 0
    saved = store.load_forecasts(tmp_path / "forecasts.json")
    assert len(saved) == 1
    summary = json.loads((tmp_path / "last_run.json").read_text(encoding="utf-8"))
    assert summary["collectors"]["fake"]["ok"] is True
    assert summary["collectors"]["fake"]["added"] == 1


def test_main_does_not_duplicate_the_same_round(tmp_path):
    collectors = {"fake": lambda today: [fake_record(2.0, today)]}
    collect.main(data_dir=tmp_path, collectors=collectors)
    collect.main(data_dir=tmp_path, collectors=collectors)  # 같은 회차 재수집
    saved = store.load_forecasts(tmp_path / "forecasts.json")
    assert len(saved) == 1  # id 가 같으므로 store.merge 가 걸러낸다


def test_main_records_collector_failure_and_continues(tmp_path):
    def boom(today):
        raise RuntimeError("site down")

    collectors = {
        "bad": boom,
        "good": lambda today: [fake_record(2.0, today)],
    }
    rc = collect.main(data_dir=tmp_path, collectors=collectors)
    assert rc == 0  # 부분 실패해도 나머지는 저장
    saved = store.load_forecasts(tmp_path / "forecasts.json")
    assert len(saved) == 1
    summary = json.loads((tmp_path / "last_run.json").read_text(encoding="utf-8"))
    assert summary["collectors"]["bad"]["ok"] is False
    assert len(summary["errors"]) == 1


def test_collectors_registry_covers_all_registered_orgs():
    assert set(collect.COLLECTORS) == {"oecd", "imf", "bok", "kdi", "kli", "kiet", "keis"}


def test_main_records_a_compact_error_without_local_paths(tmp_path):
    # last_run.json 은 공개 저장소에 커밋된다. 트레이스백을 그대로 담으면
    # 돌린 사람의 절대경로가 함께 실린다.
    def boom(today):
        raise RuntimeError("HTTP Error 502: Bad Gateway")

    collect.main(data_dir=tmp_path, collectors={"kdi": boom})
    summary = json.loads((tmp_path / "last_run.json").read_text(encoding="utf-8"))
    (error,) = summary["errors"]
    assert error == "kdi: RuntimeError: HTTP Error 502: Bad Gateway"


def edition_record(pub: date, value: float) -> ForecastRecord:
    return ForecastRecord(
        id=make_id("OECD", pub, "gdp_growth", 2027), org="OECD", org_name_ko="OECD",
        report_title="t", published_at=pub, target_year=2027,
        indicator="gdp_growth", value=value, unit="%",
        source_url="https://example.com/a", landing_url="https://example.com",
        confidence="verified", collected_at=datetime(2026, 8, 30, 16, 0),
    )


def test_a_new_edition_is_kept_even_when_the_figure_did_not_change(tmp_path):
    # published_at 이 발표일이 된 뒤로 id 가 회차마다 고정된다. 값이 그대로라고
    # 버리면 그 회차가 통째로 사라진다 — 백필로 되살려야 했던 손실이다.
    store.save_forecasts(tmp_path / "forecasts.json", [edition_record(date(2026, 6, 3), 1.9)])
    collectors = {"oecd": lambda today: [edition_record(date(2026, 12, 2), 1.9)]}
    collect.main(data_dir=tmp_path, collectors=collectors)
    saved = store.load_forecasts(tmp_path / "forecasts.json")
    assert {r.published_at for r in saved} == {date(2026, 6, 3), date(2026, 12, 2)}


def test_recollecting_the_same_edition_does_not_duplicate(tmp_path):
    collectors = {"oecd": lambda today: [edition_record(date(2026, 6, 3), 1.9)]}
    collect.main(data_dir=tmp_path, collectors=collectors)
    collect.main(data_dir=tmp_path, collectors=collectors)
    assert len(store.load_forecasts(tmp_path / "forecasts.json")) == 1


def _one_record():
    return ForecastRecord(
        id="kdi-2026-08-gdp_growth-2026", org="KDI", org_name_ko="KDI",
        report_title="KDI 경제전망, 2026년 8월", published_at=date(2026, 8, 19),
        target_year=2026, target_period="annual", indicator="gdp_growth",
        value=3.2, unit="%", source_url="https://x/y.pdf", landing_url="https://x/",
        confidence="extracted", collected_at=datetime(2026, 8, 20),
    )


def _one_rationale(text="수출 호조가 성장을 뒷받침할 것으로 전망된다."):
    return rs.Rationale(
        org="KDI", published_at=date(2026, 8, 19), indicator="gdp_growth",
        text=text, tags=["수출"], source_url="https://x/y.pdf", source_page=5)


def test_main_saves_rationales_next_to_records(tmp_path):
    collect.main(
        data_dir=tmp_path,
        collectors={"kdi": lambda today: [_one_record()]},
        rationale_collectors={"kdi": lambda today: [_one_rationale()]},
    )
    assert len(store.load_forecasts(tmp_path / "forecasts.json")) == 1
    saved = rs.load(tmp_path / "rationales.json")
    assert [r.indicator for r in saved] == ["gdp_growth"]


def test_main_keeps_an_existing_rationale(tmp_path):
    # 사람이 고친 문장을 재수집이 덮지 않는다
    rs.save(tmp_path / "rationales.json", [_one_rationale("사람이 고친 문장")])
    collect.main(
        data_dir=tmp_path,
        collectors={"kdi": lambda today: [_one_record()]},
        rationale_collectors={"kdi": lambda today: [_one_rationale("수집기가 새로 뽑은 문장")]},
    )
    assert rs.load(tmp_path / "rationales.json")[0].text == "사람이 고친 문장"


def test_a_failing_rationale_does_not_fail_the_collector(tmp_path):
    # 수치가 본체다. 근거 때문에 수치를 잃지 않는다.
    def boom(today):
        raise ValueError("본문을 못 받았다")

    collect.main(
        data_dir=tmp_path,
        collectors={"kdi": lambda today: [_one_record()]},
        rationale_collectors={"kdi": boom},
    )
    assert len(store.load_forecasts(tmp_path / "forecasts.json")) == 1
    summary = json.loads((tmp_path / "last_run.json").read_text(encoding="utf-8"))
    # 근거 실패는 errors 가 아니라 rationale_errors 에 담긴다 — errors 에
    # 섞으면 check_run.py 가 첫 콜론 앞을 수집기 이름으로 잘라 kdi 의
    # **수치** 장애로 읽고, 유예를 줘도 두 번째 루프("되살아났는데 목록에
    # 남아 있다")에 걸려 CI 가 초록으로 돌아갈 길이 없어진다.
    assert summary["errors"] == []
    assert any("kdi" in e for e in summary["rationale_errors"])
    assert summary["collectors"]["kdi"]["ok"] is True   # 수치 수집은 성공이다


def test_a_collector_without_a_rationale_entry_point_is_tolerated(tmp_path):
    # imf·oecd 처럼 근거 진입점이 없는 수집기는 rationale_collectors 에 없어도
    # main() 이 그냥 건너뛰어야 한다 — KeyError 로 죽으면 안 된다.
    rc = collect.main(
        data_dir=tmp_path,
        collectors={"oecd": lambda today: [edition_record(date(2026, 6, 3), 1.9)]},
        rationale_collectors={},
    )
    assert rc == 0
    assert store.load_forecasts(tmp_path / "forecasts.json")
    assert rs.load(tmp_path / "rationales.json") == []


def test_rationale_collectors_registry_excludes_api_only_orgs():
    # imf·oecd 는 API 로 숫자만 읽어 근거로 삼을 본문이 없다.
    assert set(collect.RATIONALE_COLLECTORS) == {"bok", "kdi", "kli", "kiet", "keis"}


# ---------------------------------------------------------------------------
# 최종 검토 Fix 5 — 손으로 고치다 깨뜨린 rationales.json 이 수치를 죽이면 안 된다.
# ---------------------------------------------------------------------------

# 설계 4.3 이 상정하는 그 편집 사고 그대로다 — source_page 에 숫자가 아니라
# 말이 들어갔고, 뒤에 끝 쉼표까지 붙었다.
MALFORMED_RATIONALES = """[
  {
    "org": "KDI",
    "published_at": "2026-08-19",
    "indicator": "gdp_growth",
    "text": "사람이 고치다 만 문장",
    "tags": [],
    "source_url": "https://example.test/report.pdf",
    "source_page": "열 번째 쪽",
  }
]
"""


def test_a_malformed_rationales_file_does_not_stop_the_numbers(tmp_path):
    # 예전에는 rs.load 가 try 밖에 있어 이 파일 하나로 실행 전체가 터졌다 —
    # forecasts.json 도 last_run.json 도 안 남았다. 근거는 곁가지고 수치가
    # 본체라는 이 브랜치의 우선순위(설계 §9)와 정반대다.
    (tmp_path / "rationales.json").write_text(MALFORMED_RATIONALES, encoding="utf-8")

    rc = collect.main(
        data_dir=tmp_path,
        collectors={"kdi": lambda today: [_one_record()]},
        rationale_collectors={"kdi": lambda today: [_one_rationale("새 문장")]},
    )

    assert rc == 0
    assert len(store.load_forecasts(tmp_path / "forecasts.json")) == 1
    summary = json.loads((tmp_path / "last_run.json").read_text(encoding="utf-8"))
    assert summary["errors"] == []
    assert any("rationales.json" in e for e in summary["rationale_errors"])


def test_a_malformed_rationales_file_is_not_overwritten(tmp_path):
    # 못 읽은 파일에 새 근거를 덮어쓰면 사람이 고치던 편집물을 우리가
    # 지우는 셈이다. 근거는 다음 실행에 다시 뽑으면 되지만 사람이 손댄
    # 문장은 그렇지 않다 — 파일이 한 글자도 안 바뀌어야 한다.
    path = tmp_path / "rationales.json"
    path.write_text(MALFORMED_RATIONALES, encoding="utf-8")

    collect.main(
        data_dir=tmp_path,
        collectors={"kdi": lambda today: [_one_record()]},
        rationale_collectors={"kdi": lambda today: [_one_rationale("새 문장")]},
    )

    assert path.read_text(encoding="utf-8") == MALFORMED_RATIONALES


def test_a_malformed_forecasts_file_still_stops_the_run(tmp_path):
    # 비대칭은 의도다 — forecasts.json 은 기계만 쓰는 파일이라 손으로 고칠
    # 일이 없고, 못 읽는다면 그건 진짜 사고다. 이쪽까지 무르게 하면 수치
    # 파일이 깨진 날 조용히 빈 파일로 다시 쓰게 된다.
    (tmp_path / "forecasts.json").write_text("{ 이건 JSON 이 아니다", encoding="utf-8")
    with pytest.raises(Exception):
        collect.main(
            data_dir=tmp_path,
            collectors={"kdi": lambda today: [_one_record()]},
        )


def test_a_rationale_only_failure_lets_the_whole_pipeline_go_green(tmp_path):
    # 두 모듈을 실제로 이어 붙여 본다 — collect.main 이 쓴 last_run.json 을
    # check_run.main 이 그대로 판정한다. 칸을 나눈 진짜 목적이 이것이라,
    # 어느 한쪽만 보는 테스트로는 "CI 가 초록으로 돌아갈 수 있다"를 못 지킨다.
    from domains.forecast.pipeline import check_run

    def boom(today):
        raise ValueError("본문을 못 받았다")

    collect.main(
        data_dir=tmp_path,
        collectors={"kdi": lambda today: [_one_record()]},
        rationale_collectors={"kdi": boom},
    )
    assert check_run.main(tmp_path / "last_run.json",
                          known_down={}, today=date(2026, 8, 30)) == 0
