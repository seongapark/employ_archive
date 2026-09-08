from domains.press.pipeline import build_data as b


def art(title, cites=True, kw=(), hits=(), tone=(), press='뉴스1', pub='2026-09-07 12:00'):
    return {'title': title, 'url': '', 'press': press, 'pub': pub,
            'cites': cites, 'why': '', 'hits': list(hits), 'tone': list(tone),
            'kw': list(kw)}


def test_signals_count_only_what_the_caller_passed():
    # build_round 는 인용 기사만 넘긴다. 이 함수는 받은 것만 센다 —
    # 필터가 두 곳에 있으면 언젠가 한 쪽만 고쳐진다.
    cited = [art('a', kw=['홈플러스']), art('b', kw=['홈플러스']), art('c', kw=['재정'])]
    outside, _ = b.signals(cited)
    assert outside == [{'w': '홈플러스', 'n': 2}]     # 1건짜리는 프레임이 아니다


def test_noise_words_are_not_frames():
    # '15개월째' 는 프레임이 아니라 기간 표기다. 잡음이 섞이면 경보가 흐려진다.
    for w in ['15개월째', '개월', '3년째', '그래픽', '지난달']:
        assert b.is_noise(w), w
    for w in ['홈플러스', '반등', 'AI', '고용한파']:
        assert not b.is_noise(w), w


def test_coverage_rolls_manufacturing_subsectors_up():
    cited = [art('반도체 호황', hits=['산업:반도체']), art('조선 회복', hits=['산업:조선'])]
    cov = b.coverage(cited)
    mfg = next(x for x in cov['industry'] if x['name'] == '제조업')
    assert mfg['n'] == 2            # 반도체·조선은 제조업으로도 센다
    semi = next(x for x in cov['industry'] if x['name'] == '반도체')
    assert semi['n'] == 1           # 그러면서 자기 칸도 유지한다


def test_coverage_reports_zero_rather_than_omitting_the_row():
    # 0건은 '안 다뤄졌다'는 사실이다. 행이 사라지면 그 사실이 안 보인다.
    cov = b.coverage([art('고용보험 가입자 증가', hits=['지표:고용보험'])])
    names = [x['name'] for x in cov['section']]
    assert names == b.SECTIONS
    assert next(x for x in cov['section'] if x['name'] == '구직급여')['n'] == 0


def test_gaps_name_the_unreported_sections():
    cov = b.coverage([art('고용보험 가입자 증가', hits=['지표:고용보험'])])
    lines = b.gaps(cov, [art('x')], '서비스업이 증가를 견인했다')
    assert any('구직급여' in ln and '0건' in ln for ln in lines)


def test_gaps_are_silent_when_there_are_no_cited_articles():
    cov = b.coverage([])
    lines = b.gaps(cov, [], '본문')
    assert not any('청년 보도' in ln for ln in lines)   # 0으로 나누지 않는다


def test_frames_call_a_word_gone_when_no_follow_up_uses_it():
    reg = [art('홈플러스 여파', kw=['홈플러스']), art('홈플러스 둔화', kw=['홈플러스'])]
    rows = b.frames(reg, [])
    assert rows[0]['kw'] == '홈플러스' and rows[0]['state'] == '소멸'


def test_frames_call_a_word_spreading_when_follow_up_matches_or_exceeds():
    reg = [art('홈플러스 여파', kw=['홈플러스']), art('홈플러스 둔화', kw=['홈플러스'])]
    fol = [art('홈플러스 후속1'), art('홈플러스 후속2'), art('홈플러스 후속3')]
    rows = b.frames(reg, fol)
    assert rows[0]['state'] == '확산' and rows[0]['later'] == 3


def test_enrich_drops_repeats_of_the_same_headline():
    # 전재·재송고로 같은 제목이 여러 번 온다. 그대로 두면 프레임 수가 부풀려진다.
    arts = [{'title': '고용보험 가입자 증가', 'press': 'A', 'pub': '2026-09-07 10:00',
             'originallink': 'u1', 'desc': ''},
            {'title': '고용보험  가입자 증가', 'press': 'B', 'pub': '2026-09-07 11:00',
             'originallink': 'u2', 'desc': ''}]
    out = b.enrich(arts, [{'n': 1, 'cites': True, 'why': ''},
                          {'n': 2, 'cites': True, 'why': ''}], {}, '본문')
    assert len(out) == 1


def test_enrich_treats_a_missing_verdict_as_not_cited():
    # 판정이 없는 회차(키가 없어 못 돌린 경우)에도 조립은 되어야 한다.
    arts = [{'title': 't', 'press': 'A', 'pub': '2026-09-07 10:00', 'link': 'u', 'desc': ''}]
    out = b.enrich(arts, [], {}, '본문')
    assert out[0]['cites'] is False


def test_issues_group_by_age_before_industry():
    # 한 기사가 두 축에 걸리면 연령을 대표축으로 쓴다 — 청년 보도가
    # 산업 이슈에 흡수되면 이 도메인이 봐야 할 것이 안 보인다.
    cited = [art('청년 제조업 취업난', hits=['산업:제조업', '연령:청년'])]
    rows = b.issues(cited)
    assert rows[0]['key'] == '청년'


def test_rivals_group_the_non_cited_by_the_llm_reason():
    # 판정 이유가 의제 이름 꼴로 오므로 그걸로 묶는다. 제목으로 묶으면
    # 매체마다 표현이 달라 안 모인다.
    no = [art('a', cites=False), art('b', cites=False), art('c', cites=False)]
    no[0]['why'] = '청년 자발적 실업급여 제도화'
    no[1]['why'] = '실업급여 확대 정책'
    no[2]['why'] = '증시 업종 등락'
    rows = b.rivals(no)
    assert rows[0]['topic'] == '구직급여' and rows[0]['n'] == 2
    assert rows[-1]['topic'] == '그 밖' and rows[-1]['n'] == 1


def test_rivals_treat_실업급여_and_구직급여_as_one_agenda():
    # 언론은 '실업급여', 보도자료는 '구직급여' 를 쓴다. 안 붙이면 한 의제가 쪼개진다.
    no = [art(str(i), cites=False) for i in range(4)]
    for a, w in zip(no, ['실업급여 확대', '구직급여 개정안', '실업급여 논쟁', '구직급여 요건']):
        a['why'] = w
    rows = b.rivals(no)
    assert [r['topic'] for r in rows] == ['구직급여']
    assert rows[0]['n'] == 4


def test_a_lone_reason_is_not_an_agenda():
    no = [art(str(i), cites=False) for i in range(3)]
    for a, w in zip(no, ['교보생명 체육대회', '증시 등락', '개인 수기']):
        a['why'] = w
    rows = b.rivals(no)
    assert [r['topic'] for r in rows] == ['그 밖'] and rows[0]['n'] == 3


def test_rivals_are_empty_when_everything_cited():
    assert b.rivals([]) == []
