"""수집기가 공유하는 얇은 네트워크 계층.

`mods.go.kr` 이 연결을 끊거나(RemoteDisconnected) 응답을 안 주는 날이 잦다 —
2026-09-04 부터 열흘 동안 회차 15번 중 11번이 eaps 실패였고, 그중 대부분이
한 번의 일시적 실패였다. KOSIS·고용노동부도 러너 네트워크가 흔들리면 같이
타임아웃한다. 한 번 실패했다고 그날 수집을 통째로 버리지 않는다.

재시도 루프를 직접 쓰지 않는다 — requests 가 이미 쓰는 urllib3 의 Retry 가
연결 실패·읽기 중단·5xx 를 지수 대기로 다시 시도한다. GET 만 재시도한다
(수집은 GET 뿐이고, 다른 메서드를 자동 재시도하면 위험하다).
"""
from __future__ import annotations

import re

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

RETRY = Retry(
    total=3,
    connect=3,
    read=3,
    backoff_factor=2,           # 2초 → 4초 → 8초
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset(["GET"]),
    raise_on_status=False,
)


def session() -> requests.Session:
    s = requests.Session()
    adapter = HTTPAdapter(max_retries=RETRY)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


# 수집기들이 같이 쓴다. 세션 하나면 연결도 재사용된다.
SESSION = session()
get = SESSION.get


# 예외 문자열에는 요청 URL 이 통째로 들어 있고, KOSIS 는 키를 질의문자열에 싣는다.
# 그 문자열을 last_run.json 에 그대로 적으면 **공개 저장소와 사이트에 키가 실린다**
# — 2026-09-10·09-11·09-13 세 회차가 실제로 그랬다. 여기서 값을 가린다.
_비밀질의 = re.compile(
    r"([?&](?:apikey|api_key|servicekey|service_key|key|token|auth)=)[^&\s'\"]+",
    re.IGNORECASE)


def 가린다(text: str) -> str:
    return _비밀질의.sub(r"\1***", str(text))


def 오류줄(이름: str, exc: BaseException) -> str:
    """last_run.json 에 남길 한 줄. 비밀은 빼고 무엇이 터졌는지는 남긴다."""
    return 가린다(f"{이름}: {type(exc).__name__}: {exc}")
