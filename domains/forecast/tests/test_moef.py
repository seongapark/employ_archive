"""기획재정부 수집기.

좌표 픽스처는 실물에서 읽은 값이다(pdf.page_words 출력). 표 머리글 모양이
회차마다 갈리는 것이 이 수집기의 핵심 위험이라 두 모양을 다 박아 둔다.
"""
from datetime import date

import pytest

from domains.forecast.pipeline.collectors import moef


def word(text, x, top, width=30.0):
    return {"text": text, "x0": x - width / 2, "x1": x + width / 2, "top": top}


# 2026년 하반기 경제성장전략 53쪽 — 연도 셋, 2026년이 분기·연간 두 열을 갖는다
#   '25년        '26년          '27년e
#   실적    1/4      연간e       연간
HALF_YEAR_HEADER = [
    word("'27년e", 465.1, 149.4), word("'26년", 353.3, 151.4), word("'25년", 244.4, 152.8),
    word("연간e", 385.9, 168.6), word("실적", 244.4, 169.7),
    word("1/4", 320.8, 170.6), word("연간", 465.1, 170.6),
]

# 2026년 경제성장전략 55쪽 — 작은따옴표가 U+2018 이고, 연간 열 이름이 '전망'이다.
#   ‘24년      ‘25년                  ‘26년
#   실적   1/4  2/4  3/4  연간e        전망
JANUARY_HEADER = [
    word("‘25년", 367.7, 172.5), word("‘24년", 230.8, 176.8), word("‘26년", 505.44, 176.8),
    word("실적", 230.8, 193.7), word("전망", 505.43999, 193.7), word("연간e", 439.9, 195.4),
    word("1/4", 290.5, 197.5), word("2/4", 340.3, 197.5), word("3/4", 390.1, 197.5),
]


def test_하반기호는_연간_열만_연도에_붙인다():
    columns = moef.annual_columns(HALF_YEAR_HEADER)
    assert [c.year for c in columns] == [2026, 2027]


def test_일월호는_따옴표가_달라도_읽고_전망_열을_연간으로_본다():
    columns = moef.annual_columns(JANUARY_HEADER)
    assert [c.year for c in columns] == [2025, 2026]


def test_연도_머리와_열이_같은_자리여도_한_해_왼쪽으로_밀리지_않는다():
    # 실측에서 '전망'(505.43999)이 ‘26년(505.44)보다 0.00001 왼쪽이었다.
    # 오른쪽 경계로 자르면 2025 로 떨어진다 — 그러면 값이 통째로 한 해씩 밀린다.
    columns = moef.annual_columns(JANUARY_HEADER)
    assert columns[-1].year == 2026


def test_연도_줄이_위아래로_흔들려도_한_줄로_묶는다():
    # 연도 줄 하나가 top 149.4~152.8(하반기호), 164.1~176.8(1월호) 로 흐른다.
    # 줄의 첫 낱말에 고정해 재면 연도가 하나 떨어져 나가 열 복원이 깨진다.
    rows = moef._rows(HALF_YEAR_HEADER)
    assert len(rows[0]) == 3, "연도 셋이 한 줄이어야 한다"


def test_지표_행을_읽는다():
    words = HALF_YEAR_HEADER + [
        word("취업자", 100, 507), word("증감(만명)", 151, 507),
        word("19", 260, 507, 14), word("18", 336, 507, 14),
        word("15", 401, 507, 14), word("17", 483, 507, 14),
    ]
    values = moef.parse_words(words)
    assert values[("emp_change", 2026, "annual")] == 15.0
    assert values[("emp_change", 2027, "annual")] == 17.0
    # 1분기 실적 18 과 전년 실적 19 는 전망이 아니다
    assert ("emp_change", 2025, "annual") not in values


def test_세모는_음수다():
    assert moef._value("△9.7") == -9.7
    assert moef._value("1,231") == 1231.0


@pytest.mark.parametrize("title", [
    "2025년 경제정책방향",
    "「2024년 하반기 경제정책방향」 및 「역동경제 로드맵」 발표",
    "「새정부 경제성장전략」 발표",
    "「2026년 경제성장전략」 발표",
    "「 2020년 경제정책방향」 발표",
])
def test_회차_제목을_받는다(title):
    assert moef.is_issue_title(title)


# 같은 검색어에 걸리지만 회차가 아닌 것들 — 전부 이름이 문장 중간에 있다
@pytest.mark.parametrize("title", [
    "국민과 함께하는 경제정책방향 플랫폼,  양방향 소통창구로 내실있게 운영",
    "경제정책방향 국민소통 플랫폼 \"함께해요 경제정책방향\" 개설",
    "홍남기 부총리-박용만 대한상의 회장, 「2020년 경제정책방향 기업인 간담회」 개최",
    "(보도설명) '26년 경제성장전략의 구체적 내용에 대해서는 결정된 바 없습니다",
    "문지성 국제경제관리관, 런던·싱가포르에서 한국경제 성장전략과 원화국제화 계획 홍보",
])
def test_회차가_아닌_글을_거른다(title):
    assert not moef.is_issue_title(title)


LIST_HTML = """
<li><h3><a href="javascript:fn_egov_select('MOSF_000000000078568');">
「2026년 하반기 경제성장전략」 발표</a></h3>
<div class="boardInfo"><div class="infoLeft"><span class="date">2026.07.14.</span>
<span class="depart">기획총괄과</span></div></div></li>
"""


def test_목록에서_회차와_발표일을_읽는다():
    rows = moef.parse_list(LIST_HTML)
    assert rows == [("MOSF_000000000078568", date(2026, 7, 14),
                     "「2026년 하반기 경제성장전략」 발표")]


VIEW_HTML = """
<span><a href="/com/cmm/fms/FileDown.do;jsessionid=ABC.node30?atchFileId=ATCH_1&amp;fileSn=1">
(보도자료) 2026년 하반기 경제성장전략.pdf
</a>80.31&nbsp;KB</span>
<div><a class="down" href="/com/cmm/fms/FileDown.do;jsessionid=ABC.node30?atchFileId=ATCH_1&amp;fileSn=1">
<span>다운로드</span></a></div>
<span><a href="/com/cmm/fms/FileDown.do;jsessionid=ABC.node30?atchFileId=ATCH_1&amp;fileSn=2">
(보도자료) 2026년 하반기 경제성장전략.hwp
</a></span>
<span><a href="/com/cmm/fms/FileDown.do;jsessionid=ABC.node30?atchFileId=ATCH_1&amp;fileSn=3">
2026년 하반기 경제성장전략_최종.pdf
</a></span>
"""


def test_첨부는_pdf_만_받고_본문을_앞에_둔다():
    got = moef.parse_attachments(VIEW_HTML)
    assert [name for name, _ in got] == [
        "2026년 하반기 경제성장전략_최종.pdf",
        "(보도자료) 2026년 하반기 경제성장전략.pdf",
    ], "hwp 는 빠지고, 전망표가 있는 본문이 먼저 와야 한다"


def test_첨부_주소에_세션토큰을_싣지_않는다():
    # source_url 은 forecasts.json 에 커밋된다. jsessionid 를 실으면 세션
    # 토큰이 저장소에 들어가고, 그 세션이 끝나면 죽는 주소가 된다.
    for _, url in moef.parse_attachments(VIEW_HTML):
        assert "jsessionid" not in url
        assert url.startswith("https://www.moef.go.kr/com/cmm/fms/FileDown.do?")


def test_검색에_searchCondition_이_빠지면_안_된다():
    # 이 파라미터가 없으면 서버가 검색어를 조용히 무시하고 전체 목록을 준다 —
    # 빈 결과가 아니라 그럴듯한 목록이 와서 눈으로는 성공처럼 보인다.
    url = moef.LIST_URL.format(keyword="경제성장전략", page=1)
    assert "searchCondition=1" in url
