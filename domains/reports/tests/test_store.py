from domains.reports.pipeline import store
from domains.reports.pipeline.models import RawReport


def rec(rid='kli-1', title='제목', abstract=None):
    return RawReport(
        id=rid, org='kli', board='kli-research', series='연구보고서',
        title=title, authors=['홍길동'], published='2025-03-01',
        date_precision='day', landing_url=f'https://example.org/{rid}',
        abstract=abstract,
    )


def test_new_records_are_added():
    merged, added = store.upsert([], [rec('kli-1'), rec('kli-2')])
    assert added == ['kli-1', 'kli-2']
    assert len(merged) == 2


def test_identical_record_is_not_rewritten():
    # 값이 같으면 같은 관측이다. collected_at 만 바뀌어 매일 커밋이 나면 안 된다.
    old = rec('kli-1')
    old.collected_at = '2026-01-01T12:00:00+09:00'
    incoming = rec('kli-1')
    incoming.collected_at = '2026-09-10T12:00:00+09:00'
    merged, added = store.upsert([old], [incoming])
    assert added == []
    assert merged[0].collected_at == '2026-01-01T12:00:00+09:00'


def test_changed_record_replaces_the_old_one():
    merged, added = store.upsert([rec('kli-1', title='옛 제목')],
                                [rec('kli-1', title='고친 제목')])
    assert merged[0].title == '고친 제목'
    assert added == []


def test_a_later_pass_can_fill_in_the_abstract():
    # 목록만 훑은 회차 뒤에 상세를 채우는 회차가 온다.
    merged, _ = store.upsert([rec('kli-1')], [rec('kli-1', abstract='초록이다')])
    assert merged[0].abstract == '초록이다'


def test_records_are_saved_sorted_and_reloaded(tmp_path):
    p = tmp_path / 'kli-research.json'
    store.save_raw(p, [rec('kli-2'), rec('kli-1')])
    again = store.load_raw(p)
    assert [r.id for r in again] == ['kli-1', 'kli-2']


def test_loading_a_missing_file_gives_an_empty_list(tmp_path):
    assert store.load_raw(tmp_path / 'none.json') == []
