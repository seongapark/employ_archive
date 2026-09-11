from domains.reports.pipeline import interests


def test_the_axis_names_are_read_from_the_headings():
    p = interests.load()
    assert 'AI·기술변화의 직종별 고용영향' in p.axes
    assert '고용행정데이터와 방법론' in p.axes
    assert len(p.axes) == 8


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
