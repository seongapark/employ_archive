"""테스트는 네트워크에 나가지 않는다.

수집기는 전부 주입 지점을 갖고 있다. 주입을 빠뜨리면 테스트가 **조용히** 게시판을
두드린다 — 느려질 뿐 아니라, 게시판이 죽은 날 아무 관계도 없는 테스트가 같이
빨개지고 원인을 찾는 데 한나절이 간다.

2026-09-11 에 실제로 그랬다. 요약 단계를 `releases.refresh` 에 붙이자 그 함수를
주입 없이 부르던 기존 테스트 다섯이 보도자료 hwpx 를 진짜로 내려받기 시작했고,
실행이 2초에서 19초가 됐다. 통과해서 더 위험했다.

`Session.request` 를 막는다 — `requests.get` 도 결국 이리로 온다.

**BaseException 으로 올린다.** 수집기의 재시도 루프는 게시판 장애를 견디려고
`except Exception` 으로 전부 삼키는데(그건 옳다), 그러면 이 가드도 같이 삼켜져
테스트가 실패 대신 재시도 sleep 만 하다 멈춘다. 처음 이 파일을 그렇게 썼다가
테스트가 2분을 넘겼다.
"""
import pytest
import requests


class NetworkUsedInTest(BaseException):
    pass


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(self, method, url, *args, **kwargs):
        raise NetworkUsedInTest(
            f"테스트가 네트워크에 나갔다({method} {url}). 주입 지점을 쓰라.")

    monkeypatch.setattr(requests.sessions.Session, "request", refuse)
