import pytest

from domains.forecast.pipeline import http


def test_returns_the_first_successful_result_without_waiting():
    waits = []
    calls = []

    def call():
        calls.append(1)
        return "ok"

    assert http.retrying(call, sleep=waits.append) == "ok"
    assert len(calls) == 1
    assert waits == []


def test_retries_a_transient_failure_and_succeeds():
    attempts = []

    def call():
        attempts.append(1)
        if len(attempts) < 3:
            raise ConnectionError("일시적 실패")
        return "ok"

    assert http.retrying(call, tries=3, sleep=lambda _: None) == "ok"
    assert len(attempts) == 3


def test_raises_the_last_error_when_every_attempt_fails():
    def call():
        raise ConnectionError("계속 실패")

    with pytest.raises(ConnectionError):
        http.retrying(call, tries=3, sleep=lambda _: None)


def test_waits_longer_between_later_attempts():
    waits = []

    def call():
        raise ConnectionError("계속 실패")

    with pytest.raises(ConnectionError):
        http.retrying(call, tries=3, wait=2.0, sleep=waits.append)
    assert waits == [2.0, 4.0]  # 마지막 시도 뒤에는 기다리지 않는다


def test_a_cloudflare_challenge_raises_blocked(monkeypatch):
    class Resp:
        status_code = 403
        headers = {"cf-mitigated": "challenge"}
    monkeypatch.setattr(http.cf_requests, "get", lambda *a, **k: Resp())
    with pytest.raises(http.Blocked):
        http.get("https://www.oecd.org/x", tries=1)
