from domains.reports.pipeline import keywords

KW = {
    '청년고용': ['청년고용', '청년 고용', '청년일자리'],
    '임금': ['임금', '최저임금'],
    '고령자': ['고령자', '중고령'],
}


def test_matching_ignores_spaces():
    # "청년고용"으로 등록해도 "청년 고용"에 걸려야 한다(검색과 같은 이유).
    assert keywords.match('청년 고용 실태 연구', KW) == ['청년고용']


def test_a_document_can_match_several_topics():
    got = keywords.match('청년고용과 최저임금의 관계', KW)
    assert set(got) == {'청년고용', '임금'}


def test_no_match_gives_an_empty_list():
    assert keywords.match('반도체 수출 동향', KW) == []


def test_topics_are_not_duplicated():
    assert keywords.match('청년고용, 청년 고용, 청년일자리', KW) == ['청년고용']


def test_shipped_keywords_cover_the_topics_the_screen_promises():
    shipped = keywords.load_keywords()
    for topic in ('청년고용', '고령자', '외국인력', '임금', '지역고용', '인력수급'):
        assert topic in shipped, f'{topic} 주제가 keywords.json 에 없다'


def test_none_of_the_shipped_topics_are_empty():
    for topic, words in keywords.load_keywords().items():
        assert words, f'{topic} 에 키워드가 없다'


def test_a_real_employment_report_title_matches():
    title = '직접일자리 사업 참여자와 구직급여 수급자 간 전이 경로와 고용 성과 분석'
    assert keywords.match(title)


def test_a_report_with_nothing_to_do_with_employment_does_not_match():
    assert keywords.match('경제적 관점에서 본 국내 재생에너지 보급 요인과 영향 분석') == []
