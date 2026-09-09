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
