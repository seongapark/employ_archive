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
    assert merged["ei"]["2026-07"]["url"] == "u"          # 기존 값은 덮이지 않고
    assert merged["ei"]["2026-06"]["url"] == "u3"         # 새 달만 들어온다
    assert existing["ei"]["2026-07"]["url"] == "u"        # 입력을 건드리지 않는다


def test_merge_fills_fields_that_the_index_did_not_used_to_carry():
    """색인이 담는 것이 늘어나면 옛 항목도 채워져야 한다.

    발표일(posted_at)을 뒤늦게 읽기 시작했을 때 기존 달이 영영 비어 있어서
    사업체노동력조사의 보도자료 보충이 조용히 건너뛰어졌다.
    """
    existing = {"est": {"2026-07": {"url": "u", "attachments": [{"type": "hwpx", "url": "f"}]}}}
    found = {"2026-07": {"url": "u2", "title": "t", "posted_at": "2026-08-27"}}
    merged = releases.merge(existing, "est", found)
    assert merged["est"]["2026-07"]["posted_at"] == "2026-08-27"   # 없던 것은 채우고
    assert merged["est"]["2026-07"]["url"] == "u"                  # 있던 것은 그대로
    assert merged["est"]["2026-07"]["attachments"] == [{"type": "hwpx", "url": "f"}]


def test_missing_attachments_lists_only_the_months_still_to_fetch():
    index = {"ei": {
        "2026-07": {"url": "u", "attachments": []},
        "2026-06": {"url": "u"},
        "2026-05": {"url": "u"},
    }}
    assert releases.missing_attachments(index, "ei") == ["2026-05", "2026-06"]
    assert releases.missing_attachments(index, "eaps") == []


# ── 네트워크 층 ───────────────────────────────────────────────────────────
# 실제 게시판을 두드리지 않는다. get 을 주입해 픽스처를 돌려주고, 몇 번 어떤
# 주소로 요청하는지까지 본다 — 무인으로 매일 도는 코드라 요청 횟수가 곧 예의다.

def fake_board(calls, *, list_fails=False):
    def get(url, params, **kw):
        calls.append((url, dict(params)))
        if list_fails:
            return None
        if "enewsList" in url:
            if params.get("pageIndex") != "1":
                return ""
            return read("moel_list_est.html") if "사업체" in params.get("searchText", "")                 else read("moel_list_ei.html")
        if "enewsView" in url:
            return read("moel_view_est.html")
        if "mods.go.kr" in url:
            return read("mods_list.html") if params.get("nPage") == "1" else ""
        return ""
    return get


def test_refresh_builds_the_index_for_all_three_sources():
    calls = []
    index, summary = releases.refresh({}, get=fake_board(calls), limit=3, summary_limit=0)
    assert set(index) == {"eaps", "est", "ei"}
    assert summary["ei"]["months"] >= 20
    assert index["eaps"]["2026-07"]["url"].endswith("list_no=446465&act=view")


def test_refresh_stops_paging_when_a_page_yields_nothing():
    """게시판을 12페이지까지 무조건 두드리지 않는다."""
    calls = []
    releases.refresh({}, get=fake_board(calls), limit=0, summary_limit=0)
    mods_pages = [p["nPage"] for u, p in calls if "mods.go.kr" in u]
    assert mods_pages == ["1", "2"], mods_pages      # 2페이지가 비면 거기서 멈춘다


def test_refresh_caps_how_many_detail_pages_it_opens():
    """첫 실행에 상세를 60건 두드리면 게시판에 무리다. 나머지는 다음 실행으로."""
    calls = []
    index, summary = releases.refresh({}, get=fake_board(calls), limit=2, summary_limit=0)
    views = [u for u, _ in calls if "enewsView" in u]
    assert len(views) == 4                            # est 2 + ei 2
    assert summary["est"]["attachments_filled"] == 2
    assert summary["est"]["pending"] > 0


def test_refresh_survives_a_dead_board():
    """게시판이 죽어도 예외를 올리지 않는다 — 색인은 숫자 수집의 전제가 아니다."""
    calls = []
    index, summary = releases.refresh({"ei": {"2026-07": {"url": "u"}}},
                                      get=fake_board(calls, list_fails=True), limit=3,
                                      summary_limit=0)
    assert summary["eaps"]["months"] == 0
    assert index["ei"]["2026-07"]["url"] == "u"       # 이미 있던 것은 지키고


def test_refresh_does_not_refetch_details_it_already_has():
    calls = []
    first, _ = releases.refresh({}, get=fake_board(calls), limit=2, summary_limit=0)
    calls.clear()
    second, summary = releases.refresh(first, get=fake_board(calls), limit=2, summary_limit=0)
    views = [u for u, _ in calls if "enewsView" in u]
    assert len(views) == 4                            # 새로 채우는 2개월치씩만
    assert summary["est"]["added"] == 0               # 목록에서 새로 들어온 달은 없다


# ── 보도자료 요약 채우기 ──────────────────────────────────────────────

def index_with(months, *, source="ei", hwpx=True):
    """첨부가 있는 달만으로 색인 한 덩어리."""
    att = [{"type": "hwpx", "url": "hwpx://%s"}] if hwpx else []
    return {source: {m: {"url": "view://" + m,
                         "attachments": [{**a, "url": a["url"] % m} for a in att]}
                     for m in months}}


def fake_hwpx(calls, *, body=None, fails=False):
    def fetch(url):
        calls.append(url)
        if fails:
            return None
        return body if body is not None else b"<no-such-thing>"
    return fetch


def real_hwpx(calls, name="ei_2026-07.hwpx"):
    payload = (FIX / name).read_bytes()

    def fetch(url):
        calls.append(url)
        return payload
    return fetch


def test_fill_summaries_reads_the_newest_month_first():
    calls = []
    index, filled = releases.fill_summaries(
        index_with(["2026-05", "2026-06", "2026-07"]), "ei",
        limit=1, fetch=real_hwpx(calls))
    assert calls == ["hwpx://2026-07"]
    assert filled == 1
    lines = index["ei"]["2026-07"]["summary"]["lines"]
    assert lines[0].startswith("▣ 고용보험 상시가입자수")


def test_fill_summaries_honours_the_limit():
    calls = []
    _, filled = releases.fill_summaries(
        index_with(["2026-05", "2026-06", "2026-07"]), "ei",
        limit=2, months=3, fetch=real_hwpx(calls))
    assert calls == ["hwpx://2026-07", "hwpx://2026-06"]
    assert filled == 2


def test_fill_summaries_skips_months_it_already_did():
    calls = []
    index = index_with(["2026-06", "2026-07"])
    index["ei"]["2026-07"]["summary"] = {"lines": ["▣ 예전에 읽은 줄"]}
    index, _ = releases.fill_summaries(index, "ei", limit=1, months=2,
                                       fetch=real_hwpx(calls))
    assert calls == ["hwpx://2026-06"]
    assert index["ei"]["2026-07"]["summary"]["lines"] == ["▣ 예전에 읽은 줄"]


def test_fill_summaries_skips_months_without_an_hwpx():
    calls = []
    index = index_with(["2026-07"], hwpx=False)
    index, filled = releases.fill_summaries(index, "ei", limit=3, fetch=real_hwpx(calls))
    assert calls == []
    assert filled == 0
    assert "summary" not in index["ei"]["2026-07"]


def test_fill_summaries_leaves_the_month_alone_when_the_download_fails():
    """받지 못한 달은 다음 실행에서 다시 시도한다."""
    calls = []
    index, filled = releases.fill_summaries(
        index_with(["2026-07"]), "ei", limit=1, fetch=fake_hwpx(calls, fails=True))
    assert filled == 0
    assert "summary" not in index["ei"]["2026-07"]


def test_fill_summaries_records_an_empty_summary_rather_than_retrying_forever():
    """원문 형식이 바뀌어 한 줄도 못 뽑으면 빈 요약을 적어 둔다.

    안 적으면 그 달이 매 실행 상한을 잡아먹어 뒤의 달들이 영영 안 채워진다.
    화면은 빈 요약을 '아직 없습니다' 로 다루고, 실행 요약이 건수를 알린다.
    """
    calls = []
    index, filled = releases.fill_summaries(
        index_with(["2026-07"]), "ei", limit=1,
        fetch=real_hwpx(calls, "est_2026-07.hwpx"))     # 출처가 어긋난 문서
    assert index["ei"]["2026-07"]["summary"]["lines"] == []
    assert filled == 1


def test_fill_summaries_does_not_touch_the_index_it_was_given():
    original = index_with(["2026-07"])
    releases.fill_summaries(original, "ei", limit=1, fetch=real_hwpx([]))
    assert "summary" not in original["ei"]["2026-07"]


def test_refresh_fills_summaries_through_the_injected_fetcher():
    calls = []
    index, summary = releases.refresh(
        {}, get=fake_board([]), limit=3,
        fetch_file=real_hwpx(calls), summary_limit=1)
    assert summary["ei"]["summaries_filled"] == 1
    assert len(calls) == 3                       # 출처마다 최신 한 회차
    assert index["ei"]["2026-07"]["summary"]["lines"]


def test_refresh_downloads_nothing_when_no_fetcher_is_given():
    """테스트가 실수로 게시판 첨부를 내려받지 않게 한다."""
    def explode(url):
        raise AssertionError("요약 단계가 주입 없이 네트워크에 나갔다: " + url)

    _, summary = releases.refresh({}, get=fake_board([]), limit=3, fetch_file=explode,
                                  summary_limit=0)
    assert summary["ei"]["summaries_filled"] == 0


def test_fill_summaries_only_looks_at_the_newest_months():
    """창 밖의 달은 아예 대상이 아니다.

    상한(limit)만 있으면 최신월을 채운 다음 실행부터 한 달씩 과거로 내려가
    결국 40개월을 다 받는다. `최근 한 달만 먼저 해 보고 늘린다` 는 결정이
    코드 어디에도 없이 며칠 만에 뒤집히는 셈이다.
    """
    calls = []
    index, filled = releases.fill_summaries(
        index_with(["2026-05", "2026-06", "2026-07"]), "ei",
        limit=3, months=1, fetch=real_hwpx(calls))
    assert calls == ["hwpx://2026-07"]
    assert filled == 1
    assert "summary" not in index["ei"]["2026-06"]


def test_widening_the_window_reaches_older_months():
    calls = []
    releases.fill_summaries(
        index_with(["2026-05", "2026-06", "2026-07"]), "ei",
        limit=3, months=3, fetch=real_hwpx(calls))
    assert calls == ["hwpx://2026-07", "hwpx://2026-06", "hwpx://2026-05"]


def test_the_window_counts_months_in_the_index_not_ones_it_already_read():
    """이미 읽은 달이 창을 밀어내면 안 된다 — 창이 한 칸씩 과거로 기어간다."""
    index = index_with(["2026-05", "2026-06", "2026-07"])
    index["ei"]["2026-07"]["summary"] = {"lines": ["▣ 읽어 둔 줄"]}
    calls = []
    _, filled = releases.fill_summaries(index, "ei", limit=3, months=1,
                                        fetch=real_hwpx(calls))
    assert calls == []
    assert filled == 0
