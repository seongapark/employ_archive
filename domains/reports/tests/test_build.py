from domains.reports.pipeline import build
from domains.reports.pipeline.boards import Board
from domains.reports.pipeline.models import RawReport

KW = {'청년고용': ['청년고용'], '임금': ['임금']}

KLI_BOARD = Board(id='kli-research', org='kli', name='연구보고서',
                  series='연구보고서', list_url='https://x/1',
                  item_re=r'(\d+)')
KDI_BOARD = Board(id='kdi-report', org='kdi', name='연구보고서',
                  series='연구보고서', list_url='https://x/2',
                  item_re=r'(\d+)')


def raw(rid, board, title='제목', abstract=None):
    return RawReport(
        id=rid, org=board.org, board=board.id, series=board.series,
        title=title, authors=[], published='2025-05-01', date_precision='day',
        landing_url=f'https://example.org/{rid}', abstract=abstract,
    )


def test_a_report_with_no_keyword_match_is_still_kept():
    # 전량 수록이다 — 키워드가 하나도 안 걸려도 담는다.
    reports, _, _ = build.build([raw('kli-1', KLI_BOARD, '노사협의회 운영실태')],
                                [KLI_BOARD], KW)
    assert [r.id for r in reports] == ['kli-1']


def test_matched_is_recorded_even_on_unfiltered_boards():
    # 주제 화면이 네 기관을 덮으려면 KLI 에도 matched 가 있어야 한다.
    reports, _, _ = build.build([raw('kli-2', KLI_BOARD, '청년고용 실태')],
                                [KLI_BOARD], KW)
    assert reports[0].matched == ['청년고용']


def test_the_abstract_counts_toward_the_match():
    reports, _, _ = build.build(
        [raw('kdi-3', KDI_BOARD, '산업구조 변화 연구', abstract='임금 격차를 다룬다')],
        [KDI_BOARD], KW)
    assert [r.id for r in reports] == ['kdi-3']


def test_every_raw_record_is_kept_regardless_of_keywords():
    # 취지가 바뀌었다 — 거르는 일은 수록이 아니라 추천이 한다.
    rows = [raw('kdi-4', KDI_BOARD, '반도체 경기와 거시경제'),
            raw('kdi-5', KDI_BOARD, '청년고용 부진의 원인')]
    kept, _, _ = build.build(rows, [KDI_BOARD], KW)
    assert sorted(r.id for r in kept) == ['kdi-4', 'kdi-5']


def test_changing_keywords_flips_the_topic_tag_without_recollecting():
    # 재수집 없이 주제 태깅이 바뀌는 성질은 그대로 지킨다. raw 는 그대로고
    # keywords 만 바뀐다.
    rows = [raw('kdi-6', KDI_BOARD, '플랫폼 종사자 실태')]
    assert build.build(rows, [KDI_BOARD], KW)[0][0].matched == []
    wider = dict(KW, 고용형태=['플랫폼 종사자'])
    assert build.build(rows, [KDI_BOARD], wider)[0][0].matched == ['고용형태']


def test_the_employment_flag_is_gone_from_the_app_record():
    kept, _, _ = build.build([raw('kli-9', KLI_BOARD, '제목')], [KLI_BOARD], KW)
    assert 'employment' not in build._light(kept[0])


def test_abstracts_are_split_out_by_id():
    kept, abstracts, _ = build.build(
        [raw('kli-3', KLI_BOARD, '제목', abstract='초록 본문')], [KLI_BOARD], KW)
    assert abstracts['kli-3']['abstract'] == '초록 본문'
    # 경량 레코드에는 초록이 없다 — 첫 화면이 그것까지 받으면 안 된다.
    assert 'abstract' not in build._light(kept[0])


def test_missing_abstract_rate_is_measured_per_org_and_series():
    rows = [raw('kli-4', KLI_BOARD, 'ㄱ', abstract='있다'),
            raw('kli-5', KLI_BOARD, 'ㄴ'),
            raw('kli-6', KLI_BOARD, 'ㄷ')]
    _, _, missing = build.build(rows, [KLI_BOARD], KW)
    cell = missing['kli']['연구보고서']
    assert cell['total'] == 3 and cell['missing'] == 2
    assert round(cell['rate'], 2) == 0.67


def test_a_raw_record_from_a_disabled_board_is_skipped():
    off = KLI_BOARD.model_copy(update={'enabled': False})
    assert build.build([raw('kli-7', off)], [off], KW)[0] == []


def test_newest_first():
    a = raw('kli-8', KLI_BOARD, '첫 번째 보고서')
    b = raw('kli-9', KLI_BOARD, '두 번째 보고서')
    b.published = '2026-01-01'
    kept, _, _ = build.build([a, b], [KLI_BOARD], KW)
    assert [r.id for r in kept] == ['kli-9', 'kli-8']


# ── 원문 PDF 에서 채운 초록 ─────────────────────────────────────────────

def test_the_pdf_bookkeeping_fields_never_reach_the_app():
    # abstract_tried·abstract_note 는 수집 살림살이다. 572건마다 실리면 목록만 커진다.
    r = raw('kli-12', KLI_BOARD)
    r.abstract_tried, r.abstract_note = True, '요약 섹션 없음'
    kept, _, _ = build.build([r], [KLI_BOARD], KW)
    light = build._light(kept[0])
    assert 'abstract_tried' not in light and 'abstract_note' not in light


def test_why_an_abstract_is_missing_is_counted():
    # 결측률만 보면 스캔본(영영 못 채움)과 아직 안 받아 본 것이 한 칸에 섞인다.
    a = raw('kli-14', KLI_BOARD, 'ㄱ'); a.abstract_tried = True; a.abstract_note = '텍스트가 없는 스캔본'
    b = raw('kli-15', KLI_BOARD, 'ㄴ')                 # 아직 안 받아 봤다
    b.file_url = 'https://example.org/b.pdf'
    c = raw('kli-16', KLI_BOARD, 'ㄷ', abstract='있다')
    kept, _, _ = build.build([a, b, c], [KLI_BOARD], KW)
    why = build.missing_reasons(kept)
    assert why == {'텍스트가 없는 스캔본': 1, '아직 안 받음': 1}


def test_the_same_study_posted_by_two_branches_is_kept_once():
    # 조사연구자료에서 실제로 7쌍 나온다 — 강원본부와 강릉본부가 같은 연구를
    # 각각 올린다. nttId 가 달라 id 로는 안 잡힌다.
    rows = [raw('bok-1', KDI_BOARD, '강원지역 주택가격이 실물경제에 미치는 영향 점검'),
            raw('bok-2', KDI_BOARD, '강원지역 주택가격이 실물경제에 미치는 영향 점검')]
    rows[0].published = '2023-07-18'
    rows[1].published = '2023-07-20'
    kept, _, _ = build.build(rows, [KDI_BOARD], KW)
    assert [r.id for r in kept] == ['bok-1']      # 이른 날짜가 원발행


def test_the_same_title_on_different_boards_is_kept_twice():
    # 게시판 간 중복은 실측 0건이었다. 우연히 제목이 같을 때 지우면 안 된다.
    other = KDI_BOARD.model_copy(update={'id': 'kdi-other'})
    rows = [raw('x-1', KDI_BOARD, '같은 제목'), raw('x-2', other, '같은 제목')]
    kept, _, _ = build.build(rows, [KDI_BOARD, other], KW)
    assert sorted(r.id for r in kept) == ['x-1', 'x-2']
