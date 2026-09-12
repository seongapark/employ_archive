from domains.reports.pipeline import interests


def test_the_axis_names_are_read_from_the_headings():
    p = interests.load()
    # 가운뎃점·중점이 든 이름이 잘리지 않고 온전히 읽히는지가 요점이다.
    assert 'AI·기술변화의 직종별 고용영향' in p.axes
    assert '고용행정데이터와 방법론' in p.axes
    # 개수를 못 박지 않는다 — 축은 사용자가 늘리는 것이고, 그때마다 테스트가
    # 깨지면 '테스트를 고치려고 개수를 맞추는' 일이 생긴다. 대신 지켜야 할
    # 성질을 잰다: 중복이 없고, 빈 이름이 없고, 하나 이상이다.
    assert len(p.axes) == len(set(p.axes)), '축 이름이 겹치면 판정이 엉뚱한 축에 묶인다'
    assert all(a.strip() for a in p.axes)
    assert p.axes


def test_the_excluded_section_is_not_an_axis():
    assert '닿지 않는 것' not in interests.load().axes


def test_the_version_comes_from_the_content(tmp_path):
    a = tmp_path / 'a.md'
    a.write_text('## 하나\n내용\n', encoding='utf-8')
    v1 = interests.load(a).version
    a.write_text('## 하나\n내용이 바뀌었다\n', encoding='utf-8')
    v2 = interests.load(a).version
    assert v1 != v2
    assert len(v1) == 8
