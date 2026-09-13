"""수집기가 쓰는 세션에 재시도가 실제로 걸려 있는지 잰다.

`requests.get` 으로 되돌아가면(또는 어댑터를 안 붙이면) 일시적 연결 끊김에
그날 수집이 통째로 비었던 상태로 돌아간다 — 2026-09 에 열흘간 11번 그랬다.
"""
from domains.employment.pipeline import check_kosis, releases
from domains.employment.pipeline.collectors import eaps, ei, est
from domains.employment.pipeline.http import SESSION


def test_세션에_재시도_어댑터가_붙어_있다():
    retry = SESSION.get_adapter("https://mods.go.kr").max_retries
    assert retry.total == 3
    assert retry.connect and retry.read
    assert retry.backoff_factor > 0


def test_GET_만_자동_재시도한다():
    retry = SESSION.get_adapter("https://mods.go.kr").max_retries
    assert set(retry.allowed_methods) == {"GET"}


def test_수집기가_맨_requests_를_직접_쓰지_않는다():
    for mod in (eaps, ei, est, releases, check_kosis):
        assert not hasattr(mod, "requests"), mod.__name__
        assert mod.SESSION is SESSION, mod.__name__
