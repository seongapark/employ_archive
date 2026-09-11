from domains.press.pipeline import build_data as b


def art(title, cites=True, kw=(), hits=(), tone=(), press='뉴스1', pub='2026-09-07 12:00',
        stance='', focus='주제'):
    return {'title': title, 'url': '', 'press': press, 'pub': pub,
            'cites': cites, 'why': '', 'hits': list(hits), 'tone': list(tone),
            'kw': list(kw), 'stance': stance, 'focus': focus if cites else ''}


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


def test_a_passing_mention_is_not_a_cited_article_on_screen():
    # 「'싼 게 비지떡' 청년 주거 엇박」은 도입부에 수치를 끌어다 썼다. 인용은
    # 맞지만 이 보도자료의 후속 보도는 아니다 — 세면 번진 범위가 부풀어 보인다.
    assert b.is_cited(art('본론', focus='주제'))
    assert not b.is_cited(art('곁들임', focus='언급'))
    assert not b.is_cited(art('딴 얘기', cites=False))


def test_old_verdicts_without_a_weight_still_count_as_cited():
    # 무게는 나중에 붙인 항목이다. 없다고 빈 화면을 주지는 않는다.
    old = {'title': 't', 'cites': True}
    assert b.is_cited(old)


def test_stance_says_which_way_the_coverage_leaned():
    cited = [art('a', stance='긍정'), art('b', stance='긍정'), art('c', stance='부정'),
             art('d', stance='중립')]
    got = b.stance(cited)
    assert got['label'] == '긍정 우세'
    assert (got['pos'], got['neg'], got['neu'], got['judged']) == (2, 1, 1, 4)


def test_stance_calls_a_tie_a_tie():
    got = b.stance([art('a', stance='긍정'), art('b', stance='부정')])
    assert got['label'] == '엇갈림'


def test_stance_without_verdicts_says_so_instead_of_guessing_neutral():
    # LLM 키가 없으면 논조가 빈 채로 온다. '중립'으로 접으면 판정이 없는
    # 회차와 정말 중립인 회차가 화면에서 똑같아 보인다.
    got = b.stance([art('a'), art('b')])
    assert got['label'] == '판정 없음'
    assert got['judged'] == 0 and got['total'] == 2


def test_stance_ignores_values_the_model_was_not_supposed_to_send():
    got = b.stance([art('a', stance='약간 긍정'), art('b', stance='부정')])
    assert (got['judged'], got['label']) == (1, '부정 우세')


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


def test_trend_series_stops_at_the_last_day_actually_collected():
    # 아직 오지 않은 날을 0 으로 이으면 「사라졌다」로 읽힌다.
    reg = [art('반등', kw=['반등'], pub='2026-09-07 12:00'),
           art('반등 둘', kw=['반등'], pub='2026-09-07 13:00')]
    rows = b.frames(reg, [], '2026-09-07', covered=3)
    assert rows[0]['series'] == [2, 0, 0, 0]


def test_covered_days_takes_the_earlier_of_window_end_and_last_run():
    # 구간이 D+21 까지 열려 있어도 오늘이 D+4 면 거기까지가 진짜다.
    assert b.covered_days('2026-09-07', {
        'window': ['2026-09-08', '2026-09-28'], 'at': '2026-09-11 10:53'}) == 4
    assert b.covered_days('2026-08-10', {
        'window': ['2026-08-11', '2026-08-25'], 'at': '2026-09-11 10:00'}) == 15
    assert b.covered_days('2026-09-07', None) == 0


def test_frames_call_a_word_gone_when_no_follow_up_uses_it():
    reg = [art('홈플러스 여파', kw=['홈플러스']), art('홈플러스 둔화', kw=['홈플러스'])]
    rows = b.frames(reg, [])
    assert rows[0]['kw'] == '홈플러스' and rows[0]['state'] == '소멸'


def test_frames_call_a_word_spreading_when_follow_up_matches_or_exceeds():
    reg = [art('홈플러스 여파', kw=['홈플러스']), art('홈플러스 둔화', kw=['홈플러스'])]
    fol = [art('홈플러스 후속%d' % i, kw=['홈플러스']) for i in (1, 2, 3)]
    rows = b.frames(reg, fol)
    assert rows[0]['state'] == '확산' and rows[0]['later'] == 3


def test_frames_track_industry_and_age_not_only_words_outside_the_release():
    # 「제조업」은 보도자료 항목사전에 있어 kw 가 아니라 hits 로 온다. 밖 표현만
    # 세던 때에는 정기 8건·후속 7건으로 계속 나오는데도 그래프에 없었다.
    reg = [art('제조업 가입자 증가', hits=['산업:제조업']),
           art('제조업 반등', hits=['산업:제조업'], kw=['반등'])]
    fol = [art('제조업 고용 회복', hits=['산업:제조업'])]
    rows = {r['kw']: r for r in b.frames(reg, fol)}
    assert rows['제조업']['d0'] == 2 and rows['제조업']['later'] == 1


def test_frames_leave_out_the_indicator_axis():
    # 「고용보험」·「가입자」는 보도자료 제목 그 자체라 거의 모든 기사에 있다.
    # 늘 1등으로 서서 진짜 신호를 덮는다.
    reg = [art('고용보험 가입자 증가', hits=['지표:고용보험', '지표:가입자']),
           art('고용보험 가입자 감소', hits=['지표:고용보험', '지표:가입자'])]
    assert b.frames(reg, []) == []


def test_frames_merge_names_that_mean_the_same_axis():
    # 「29세이하」와 「청년」이 갈리면 한 축이 두 선으로 쪼개진다.
    # 괄호는 항목사전이 붙인 표준분류라 뗀다.
    reg = [art('29세이하 감소', hits=['연령:29세이하']),
           art('청년 감소', hits=['연령:청년']),
           art('반도체 증가', hits=['산업:반도체(전자·통신)']),
           art('반도체 호황', hits=['산업:반도체(전자·통신)'])]
    rows = {r['kw']: r['d0'] for r in b.frames(reg, [])}
    assert rows['청년'] == 2 and rows['반도체'] == 2
    assert '29세이하' not in rows


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


def test_verdicts_are_matched_by_title_not_by_position():
    # 재수집하면 검색 결과의 순서와 개수가 달라진다. 번호로 이으면 3번 기사의
    # 판정이 5번 기사에 붙고 아무 에러도 안 난다 — 조용한 오염이다.
    arts = [{'title': '나중에 들어온 기사', 'press': 'A', 'pub': '2026-09-07 09:00',
             'link': 'u0', 'desc': ''},
            {'title': '고용보험 가입자 증가', 'press': 'B', 'pub': '2026-09-07 12:00',
             'link': 'u1', 'desc': ''}]
    verdicts = [{'n': 1, 'cites': True, 'why': '27만8천명', 'title': '고용보험 가입자 증가'}]
    out = b.enrich(arts, verdicts, {}, '본문')
    assert out[0]['cites'] is False and out[0]['judged'] is False
    assert out[1]['cites'] is True and out[1]['why'] == '27만8천명'


def test_old_verdict_files_without_titles_still_line_up_by_number():
    arts = [{'title': 't1', 'press': 'A', 'pub': '', 'link': '', 'desc': ''},
            {'title': 't2', 'press': 'B', 'pub': '', 'link': '', 'desc': ''}]
    out = b.enrich(arts, [{'n': 2, 'cites': True}], {}, '본문')
    assert out[1]['cites'] is True and out[0]['cites'] is False


def test_an_article_with_no_verdict_is_marked_unjudged():
    arts = [{'title': 't', 'press': 'A', 'pub': '', 'link': '', 'desc': ''}]
    assert b.enrich(arts, [], {}, '본문')[0]['judged'] is False
