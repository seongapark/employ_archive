import pytest

from domains.reports.pipeline import models


def test_full_date_keeps_day_precision():
    assert models.normalize_published('2025-12-03') == ('2025-12-03', 'day')
    assert models.normalize_published('2025.12.03') == ('2025-12-03', 'day')
    assert models.normalize_published('2025. 12. 03.') == ('2025-12-03', 'day')


def test_year_month_fills_to_month_end():
    # 정렬이 깨지지 않게 채우되, 채웠다는 사실을 precision 이 말한다.
    assert models.normalize_published('2025-12') == ('2025-12-31', 'month')
    assert models.normalize_published('2025.02') == ('2025-02-28', 'month')
    assert models.normalize_published('2024.02') == ('2024-02-29', 'month')  # 윤년


def test_year_only_fills_to_year_end():
    assert models.normalize_published('2025') == ('2025-12-31', 'year')
    assert models.normalize_published('2025년') == ('2025-12-31', 'year')


def test_unparseable_date_raises():
    # 조용히 오늘 날짜를 넣으면 타임라인 맨 위에 가짜가 얹힌다.
    with pytest.raises(ValueError):
        models.normalize_published('발간예정')


def test_report_id_uses_the_number_the_org_gave():
    assert models.report_id('kli', '10302') == 'kli-10302'


def test_raw_report_has_no_verdict_fields():
    # 판정은 build 가 붙인다. raw 에 있으면 수집이 판정한 것이다.
    assert 'employment' not in models.RawReport.model_fields
    assert 'matched' not in models.RawReport.model_fields
    assert 'employment' in models.Report.model_fields


def test_report_rejects_dates_before_the_cutoff():
    with pytest.raises(ValueError):
        models.RawReport(
            id='kli-1', org='kli', board='kli-research', series='연구보고서',
            title='제목', authors=[], published='2020-12-31',
            date_precision='day', landing_url='https://example.org/1',
        )
