"""보도자료 요약 발췌. 세 출처 모두 실물 hwpx 픽스처로 시험한다.

요약은 **원문에 이미 있는 줄**을 뽑아 오는 것이다. 문장을 새로 짓지 않으므로
기대값을 원문과 글자 단위로 맞춰 둔다 — 규칙이 흔들리면 여기서 걸린다.
"""
from pathlib import Path

import pytest

from domains.employment.pipeline import summary

FIXTURES = Path(__file__).parent / "fixtures"


def lines_of(name: str, source: str) -> list[str]:
    return summary.from_hwpx(source, (FIXTURES / name).read_bytes())


def test_eaps_takes_the_summary_box_not_the_table_of_contents():
    lines = lines_of("eaps_2026-08.hwpx", "eaps")
    assert lines == [
        "□ 15~64세 고용률(OECD비교기준)은 70.4%로 전년동월대비 0.5%p 상승",
        "○ 청년층(15~29세) 고용률은 44.1%로 전년동월대비 1.0%p 하락",
        "□ 실업률은 2.0%로 전년동월과 동일",
        "○ 청년층(15~29세) 실업률은 5.4%로 전년동월대비 0.5%p 상승",
        "□ 취업자는 2,915만 1천명으로 전년동월대비 18만 4천명 증가",
        "○ 15~64세 고용률(OECD비교기준)은 50대, 40대 등에서 상승하여 전년동월대비 0.5%p 상승",
    ]


def test_ei_takes_the_주요특징_block():
    lines = lines_of("ei_2026-07.hwpx", "ei")
    assert lines[0] == "▣ 고용보험 상시가입자수는 7개월 연속 20만명 후반대 증가"
    assert lines[-1] == "* 고용24를 통한 구인동향 해석 시, 미이용 기업의 동향을 함께 고려할 필요"
    assert len(lines) == 7


def test_est_keeps_reading_past_the_tables_between_bullets():
    # 사업체는 불릿 사이에 표가 끼어 있다. 불릿이 끊기면 멈추는 규칙으로 읽으면
    # 종사상지위별 한 줄만 건지고 규모별·산업별을 놓친다.
    lines = lines_of("est_2026-07.hwpx", "est")
    assert lines[0].startswith("□ (총괄)")
    assert any(line.startswith("ㅇ (규모별)") for line in lines)
    assert any(line.startswith("ㅇ (비제조업)") for line in lines)


def test_est_stops_before_the_next_section():
    # 입·이직자 절에도 "□ (총괄)" 이 있다. 거기까지 삼키면 요약이 아니라 본문이 된다.
    lines = lines_of("est_2026-07.hwpx", "est")
    assert not any("입직자는" in line for line in lines)


def test_returns_nothing_when_the_marker_is_missing():
    # 원문 형식이 바뀌면 빈 리스트다. 아무 줄이나 집어 오면 화면이 조용히
    # 엉뚱한 문장을 요약이라 말하게 된다.
    assert summary.extract("eaps", ["표지", "목차", "□ 통계표"]) == []


def test_unknown_source_returns_nothing():
    assert summary.extract("wat", ["□ 무언가"]) == []


def test_caps_the_number_of_lines():
    paragraphs = ["2026년 8월 고용동향(요약)"] + [f"□ {i}번째 줄" for i in range(20)]
    assert len(summary.extract("eaps", paragraphs)) == summary.MAX_LINES


@pytest.mark.parametrize("source", ["eaps", "ei", "est"])
def test_every_line_is_verbatim_from_the_document(source):
    name = {"eaps": "eaps_2026-08.hwpx", "ei": "ei_2026-07.hwpx",
            "est": "est_2026-07.hwpx"}[source]
    from domains.employment.pipeline import hwpx
    data = (FIXTURES / name).read_bytes()
    original = set(hwpx.paragraphs(data))
    assert set(summary.from_hwpx(source, data)) <= original
