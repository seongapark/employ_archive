# -*- coding: utf-8 -*-
"""KOSIS 대조 가드. 이 가드가 틀리면 **수집 전체가 멈춘다** — 조용히 지나가는
쪽이 아니라 시끄럽게 실패하는 쪽이라, 오판 하나가 그날 회차를 통째로 버린다.
"""
from datetime import date, datetime

import pytest

from domains.employment.pipeline import check_kosis
from domains.employment.pipeline.models import SeriesRecord

NOW = datetime(2026, 9, 12, 3, 0, 0)


def rec(series, value, *, period='2026-08', unit='천명'):
    return SeriesRecord(
        id=f'eaps-{period}-{series}-total', source='eaps', series=series,
        breakdown='total', period=period, value=value, unit=unit,
        released_at=date(2026, 9, 10), release_url='https://kostat.go.kr/x',
        collected_at=NOW)


def test_it_compares_the_headcount_not_whatever_series_sorts_last():
    # 같은 달에 여덟 줄(취업자·고용률·실업률…)이 있다. 지표를 거르지 않으면
    # max() 가 그중 아무거나 집어 고용률 63.3(%)을 KOSIS 취업자 29,151(천명)과
    # 견준다 — 2026-09-12 수집이 실제로 그렇게 죽었다.
    records = [rec('employment_rate', 63.3, unit='%'),
               rec('unemployment_rate', 2.0, unit='%'),
               rec('headcount', 29151.0)]
    got = check_kosis.check(records, api_key='k',
                            get=lambda *a, **k: [{'DT': '29151'}])
    assert got == '2026-08 29151.0 일치'


def test_a_real_mismatch_still_fails_loudly():
    # 표가 바뀌는 사고를 잡는 것이 이 가드의 목적이다. 거르기를 더한 뒤에도
    # 진짜 불일치는 그대로 예외여야 한다.
    records = [rec('headcount', 29151.0)]
    with pytest.raises(ValueError, match='DT_1DA7002S'):
        check_kosis.check(records, api_key='k',
                          get=lambda *a, **k: [{'DT': '28000'}])


def test_without_a_headcount_row_it_reports_nothing_instead_of_guessing():
    # 취업자 줄이 없으면 대조할 상대가 없다. 다른 지표로 대신 견주면
    # 그게 바로 위의 오판이다.
    assert check_kosis.check([rec('employment_rate', 63.3, unit='%')],
                             api_key='k',
                             get=lambda *a, **k: [{'DT': '29151'}]) is None


def test_a_dead_kosis_does_not_fail_the_round():
    # 대조를 못 한 것과 대조에 실패한 것은 다르다.
    got = check_kosis.check([rec('headcount', 29151.0)], api_key='k',
                            get=lambda *a, **k: [])
    assert got is not None and '대조 못 함' in got
