"""추천 판정. call 을 주입하므로 네트워크를 쓰지 않는다."""
import json
import re

import pytest

from domains.reports.pipeline import recommend
from domains.reports.pipeline.interests import Profile

PROFILE = Profile(text='## 청년 고용\n청년 일자리.\n## 임금·근로조건\n임금 격차.\n',
                  axes=['청년 고용', '임금·근로조건'], version='abcd1234')

ROWS = [
    {'id': 'bok-1', 'org': 'BOK', 'series': 'BOK 이슈노트',
     'title': '청년고용 위축, AI탓인가?', 'abstract': '경력 사다리 변화를 분석한다.'},
    {'id': 'kdi-2', 'org': 'KDI', 'series': '연구보고서',
     'title': '가계부채 리스크 평가', 'abstract': '가구 단위 신용위험.'},
]


def test_the_prompt_carries_the_profile_and_numbers_every_row():
    p = recommend.build_prompt(PROFILE, ROWS)
    assert '청년 고용' in p
    assert '1. ' in p and '2. ' in p
    assert '청년고용 위축' in p
    # id 를 모델에 주지 않는다 — 지어내면 엉뚱한 레코드에 붙는다.
    assert 'bok-1' not in p


def test_a_well_formed_response_is_read():
    body = json.dumps([
        {'n': 1, 'pick': True, 'axis': '청년 고용', 'why': '청년 경력 사다리를 분해'},
        {'n': 2, 'pick': False, 'axis': '', 'why': '가계부채 — 고용과 무관'},
    ], ensure_ascii=False)
    got = recommend.parse_response(body, 2, PROFILE.axes)
    assert got[0].pick is True and got[0].axis == '청년 고용'
    assert got[1].pick is False


def test_a_fenced_response_is_read():
    body = '```json\n[{"n":1,"pick":true,"axis":"청년 고용","why":"ㄱ"},' \
           '{"n":2,"pick":false,"axis":"","why":"ㄴ"}]\n```'
    assert len(recommend.parse_response(body, 2, PROFILE.axes)) == 2


def test_a_missing_row_is_an_error_not_a_silent_false():
    body = json.dumps([{'n': 1, 'pick': True, 'axis': '청년 고용', 'why': 'ㄱ'}])
    with pytest.raises(ValueError, match='빠진'):
        recommend.parse_response(body, 2, PROFILE.axes)


def test_an_unknown_axis_is_an_error():
    body = json.dumps([{'n': 1, 'pick': True, 'axis': '없는축', 'why': 'ㄱ'}],
                      ensure_ascii=False)
    with pytest.raises(ValueError, match='축'):
        recommend.parse_response(body, 1, PROFILE.axes)


def test_a_pick_without_a_reason_is_an_error():
    body = json.dumps([{'n': 1, 'pick': True, 'axis': '청년 고용', 'why': ''}],
                      ensure_ascii=False)
    with pytest.raises(ValueError, match='이유'):
        recommend.parse_response(body, 1, PROFILE.axes)


def test_judge_splits_into_batches_and_renumbers_globally():
    # 25건이면 20 + 5 두 묶음이다. 묶음마다 n 은 1부터 다시 세지만,
    # 돌려줄 때는 전체 기준 번호여야 호출자가 id 에 되맞출 수 있다.
    sizes = []

    def fake_call(prompt):
        n = sum(1 for line in prompt.splitlines()
                if re.match(r'^\d+\. \[', line))
        sizes.append(n)
        return json.dumps([{'n': i + 1, 'pick': False, 'axis': '', 'why': 'ㄱ'}
                           for i in range(n)], ensure_ascii=False)

    rows = [dict(ROWS[0], id=f'r-{i}') for i in range(25)]
    got = recommend.judge(PROFILE, rows, call=fake_call, log=lambda *_: None)
    assert sizes == [20, 5]
    assert [v.n for v in got] == list(range(1, 26))
