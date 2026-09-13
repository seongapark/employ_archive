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


def test_KOSIS_키가_오류줄에_안_남는다():
    """공개 저장소·사이트에 실리는 문자열이다 — 2026-09 에 세 회차가 키를 실었다."""
    from domains.employment.pipeline.http import 오류줄

    url = ("https://kosis.kr/openapi/Param/statisticsParameterData.do"
           "?method=getList&apiKey=ZjI2NzMzNDFjOGZj%3D&orgId=118")
    줄 = 오류줄("est", ConnectionError(f"Max retries exceeded with url: {url}"))
    assert "ZjI2" not in 줄
    assert "apiKey=***" in 줄
    assert "orgId=118" in 줄          # 진단에 필요한 나머지는 남는다
    assert 줄.startswith("est: ConnectionError:")
