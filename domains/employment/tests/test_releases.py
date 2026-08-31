import io
from pathlib import Path

import pytest

from domains.employment.pipeline import releases

FIX = Path(__file__).parent / "fixtures"


def read(name):
    return io.open(FIX / name, encoding="utf-8").read()


@pytest.fixture(scope="module")
def mods():
    return releases.mods_list(read("mods_list.html"))


@pytest.fixture(scope="module")
def est():
    return releases.moel_list(read("moel_list_est.html"), must_contain="사업체노동력조사")


@pytest.fixture(scope="module")
def ei():
    return releases.moel_list(read("moel_list_ei.html"), must_contain="고용행정")


def test_period_reads_both_two_and_four_digit_years():
    # 국가데이터처는 `26년 7월 고용동향` 처럼 두 자리 연도를 쓰기도 한다
    assert releases.period_of("26년 7월 고용동향") == "2026-07"
    assert releases.period_of("2026년 6월 고용동향") == "2026-06"
    assert releases.period_of("2026년 12월 고용동향") == "2026-12"


def test_period_refuses_titles_without_a_month():
    assert releases.period_of("2026년 상반기 직종별사업체노동력조사 결과 발표") is None
    assert releases.period_of("2024년 일자리이동통계 결과") is None
    assert releases.period_of("2026년 13월 고용동향") is None


def test_mods_takes_only_the_monthly_고용동향_posts(mods):
    """같은 게시판의 부가조사·지역별고용조사가 섞여 들어오면 안 된다.

    이들도 `2026년 5월` 을 제목에 달고 있어서 기간만으로는 갈리지 않는다 —
    섞이면 한 달에 엉뚱한 글이 잡혀 `보도자료` 가 다른 조사로 간다.
    """
    assert mods, "고용동향 회차를 하나도 못 찾았다"
    for period, post in mods.items():
        assert post["title"].replace(" ", "").endswith("고용동향"), post["title"]
    assert "2026-07" in mods
    assert "446465" in mods["2026-07"]["url"]


def test_mods_carries_attachments_from_the_list_page(mods):
    """국가데이터처는 첨부가 목록에 있다 — 상세를 두드릴 필요가 없다."""
    kinds = [a["type"] for a in mods["2026-07"]["attachments"]]
    assert kinds == ["hwpx", "pdf", "xlsx"]
    for a in mods["2026-07"]["attachments"]:
        assert a["url"].startswith("https://mods.go.kr/boardDownload.es?")
        assert "list_no=446465" in a["url"]


def test_moel_filters_out_the_regional_and_occupational_surveys(est):
    """`지역별사업체노동력조사`·`직종별사업체노동력조사` 는 분기·반기 자료다."""
    assert est
    for period, post in est.items():
        assert "사업체노동력조사" in post["title"]
    # 2026-07 글의 제목은 월간과 지역별을 함께 담는다. 앞의 연월이 기준월이다.
    assert est["2026-07"]["title"].startswith("2026년 7월 사업체노동력조사")
    # 상반기 직종별 회차는 월이 없어 색인에 들어오지 않는다
    assert not any("직종별" in p["title"] and "상반기" in p["title"] for p in est.values())


def test_moel_index_covers_a_couple_of_years(est, ei):
    assert len(est) >= 20 and len(ei) >= 20
    assert "2026-07" in ei and "2026-06" in ei


def test_moel_attachments_keep_one_file_per_kind():
    """같은 파일이 이름 링크와 `다운로드` 링크로 두 번 나온다."""
    files = releases.moel_attachments(read("moel_view_est.html"))
    assert [a["type"] for a in files] == ["hwpx", "pdf"]
    assert len({a["url"] for a in files}) == 2
    for a in files:
        assert a["url"].startswith("https://www.moel.go.kr/common/downloadFile.do?")


def test_merge_does_not_overwrite_a_month_that_already_has_attachments():
    """목록만 보고 덮어쓰면 상세에서 받아둔 첨부가 날아간다."""
    existing = {"ei": {"2026-07": {"url": "u", "title": "t", "attachments": [{"type": "hwpx", "url": "f"}]}}}
    found = {"2026-07": {"url": "u2", "title": "t2"}, "2026-06": {"url": "u3", "title": "t3"}}
    merged = releases.merge(existing, "ei", found)
    assert merged["ei"]["2026-07"]["attachments"] == [{"type": "hwpx", "url": "f"}]
    assert merged["ei"]["2026-07"]["url"] == "u"          # 기존 항목은 그대로
    assert merged["ei"]["2026-06"]["url"] == "u3"         # 새 달만 들어온다
    assert existing["ei"]["2026-07"]["url"] == "u"        # 입력을 건드리지 않는다


def test_missing_attachments_lists_only_the_months_still_to_fetch():
    index = {"ei": {
        "2026-07": {"url": "u", "attachments": []},
        "2026-06": {"url": "u"},
        "2026-05": {"url": "u"},
    }}
    assert releases.missing_attachments(index, "ei") == ["2026-05", "2026-06"]
    assert releases.missing_attachments(index, "eaps") == []
