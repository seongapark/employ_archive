import pytest

from domains.reports.pipeline import http


class FakeResp:
    def __init__(self, content: bytes, encoding: str | None = None):
        self.content = content
        self.encoding = encoding

    def raise_for_status(self):
        return None


def test_retries_a_transient_failure():
    calls = []

    def flaky(url, timeout):
        calls.append(url)
        if len(calls) < 3:
            raise RuntimeError('502')
        return FakeResp('좋다'.encode('utf-8'), 'utf-8')

    text = http.get_text('https://x/1', fetch=flaky, sleep=lambda _: None)
    assert text == '좋다'
    assert len(calls) == 3


def test_gives_up_after_the_last_try():
    def always(url, timeout):
        raise RuntimeError('down')

    with pytest.raises(RuntimeError):
        http.get_text('https://x/1', tries=2, fetch=always, sleep=lambda _: None)


def test_decodes_euc_kr_when_the_server_says_so():
    body = '고용'.encode('euc-kr')
    resp = FakeResp(body, 'euc-kr')
    assert http.get_text('https://x/1', fetch=lambda u, timeout: resp,
                         sleep=lambda _: None) == '고용'


def test_falls_back_to_euc_kr_when_utf8_fails():
    # 인코딩을 안 알려주는 국내 사이트가 있다. utf-8 로 깨지면 euc-kr 을 본다.
    body = '고용노동'.encode('euc-kr')
    resp = FakeResp(body, None)
    assert http.get_text('https://x/1', fetch=lambda u, timeout: resp,
                         sleep=lambda _: None) == '고용노동'


def test_throttle_waits_between_requests():
    slept = []
    clock = iter([0.0, 0.2, 1.4])
    t = http.Throttle(delay=1.0, sleep=slept.append, now=lambda: next(clock))
    t.wait()          # 첫 요청은 안 기다린다
    t.wait()          # 0.2초밖에 안 지났으니 0.8초 기다린다 (그때가 1.0초)
    t.wait()          # 1.4초, 직전 요청이 1.0초였으니 0.6초 더 기다린다
    assert slept == [pytest.approx(0.8), pytest.approx(0.6)]


def test_a_file_url_with_a_korean_name_is_percent_encoded():
    # KLI 의 fileNameOrg, KEIS 의 fn 질의에 한글과 공백이 그대로 들어 있다.
    # 인코딩하지 않으면 요청이 만들어지기 전에 깨진다(2026-09-10 실측).
    seen = []

    def spy(url, timeout):
        seen.append(url)
        return FakeResp(b'%PDF-1.7')

    url = 'https://www.kli.re.kr/down?fileNameOrg=임금정보브리프 제90호.pdf&filePath1=a/b'
    assert http.get_bytes(url, fetch=spy) == b'%PDF-1.7'
    assert '%EC%9E%84' in seen[0] and ' ' not in seen[0]
    assert seen[0].startswith('https://www.kli.re.kr/down?')
    assert '&' in seen[0] and '=' in seen[0], '질의 구분자까지 인코딩하면 주소가 망가진다'


def test_bytes_are_not_decoded():
    # PDF 는 텍스트가 아니다. 인코딩을 건드리면 파일이 깨진다.
    body = bytes(range(256))
    assert http.get_bytes('https://x/f.pdf', fetch=lambda u, timeout: FakeResp(body)) == body


def test_a_file_download_retries_too():
    calls = []

    def flaky(url, timeout):
        calls.append(url)
        if len(calls) < 2:
            raise RuntimeError('502')
        return FakeResp(b'%PDF-')

    assert http.get_bytes('https://x/f.pdf', fetch=flaky, sleep=lambda _: None) == b'%PDF-'
    assert len(calls) == 2
