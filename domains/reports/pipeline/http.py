"""수집기가 공유하는 얇은 네트워크 계층.

기관 사이트는 간헐적으로 502를 준다. 한 번의 일시적 실패로 그 게시판이 통째로
비지 않도록 몇 번 다시 시도한다. 인코딩을 안 알려주는 국내 사이트가 있어
utf-8 → euc-kr 순으로 본다.
"""
from __future__ import annotations

import time
from typing import Callable, Optional
from urllib.parse import quote

from curl_cffi import requests as cf_requests


# 재시도 사이 간격(초). **초 단위로 끝낸다.**
#
# 2026-09-14 에 두 번째를 5분으로 늘린 적이 있다. KEIS 게시판 6개가 한꺼번에
# 연결 시간초과로 죽어서, 차단이 풀릴 시간을 주자는 것이었다. 안 풀렸다 —
# 다음 회차는 55분을 돌고 똑같이 실패했고, 그중 48분이 죽은 연결을 기다린
# 시간이었다. KEIS 는 해외 IP 를 전면 차단한다(2026-09-15 에 55개국에서
# 확인, 성공 0). 기다려서 될 일이 아니었다.
#
# 그래서 수집을 국내에서 돌리기로 하고(collect-local.ps1), 간격은 원래대로
# 되돌린다. 국내에서 나는 실패는 502 같은 한순간짜리라 초 단위가 맞다.
BACKOFF = (2.0, 4.0)


def _backoff(attempt: int) -> float:
    """attempt 회째 실패 뒤 쉴 시간. 표를 넘어가면 마지막 값을 쓴다."""
    return BACKOFF[min(attempt, len(BACKOFF)) - 1]


def _default_fetch(url: str, timeout: int):
    return cf_requests.get(url, impersonate='chrome', timeout=timeout)


def _decode(content: bytes, encoding: Optional[str]) -> str:
    order = [encoding] if encoding else []
    order += ['utf-8', 'euc-kr', 'cp949']
    for enc in order:
        if not enc:
            continue
        try:
            return content.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return content.decode('utf-8', errors='replace')


def get_text(url: str, *, timeout: int = 60, tries: int = 3,
             sleep: Callable[[float], None] = time.sleep,
             fetch: Optional[Callable] = None) -> str:
    call = fetch or _default_fetch
    last: Optional[Exception] = None
    for attempt in range(1, tries + 1):
        try:
            resp = call(url, timeout=timeout)
            resp.raise_for_status()
            return _decode(resp.content, getattr(resp, 'encoding', None))
        except Exception as exc:       # noqa: BLE001 — 무엇이든 다시 시도한다
            last = exc
            if attempt == tries:
                break
            sleep(_backoff(attempt))
    raise last                          # type: ignore[misc]


class Throttle:
    """요청 사이 간격을 지킨다. 게시판 예의는 코드로 강제한다."""

    def __init__(self, delay: float = 1.0,
                 sleep: Callable[[float], None] = time.sleep,
                 now: Callable[[], float] = time.monotonic):
        self.delay = delay
        self._sleep = sleep
        self._now = now
        self._last: Optional[float] = None

    def wait(self) -> None:
        # 시계는 한 번만 읽는다. 잔 시간은 시계를 다시 읽는 대신 더해 둔다 —
        # 그래야 다음 간격이 "요청을 보낸 시각" 기준으로 재진다.
        t = self._now()
        if self._last is not None:
            gap = self.delay - (t - self._last)
            if gap > 0:
                self._sleep(gap)
                t += gap
        self._last = t


def get_bytes(url: str, *, timeout: int = 180, tries: int = 3,
              sleep: Callable[[float], None] = time.sleep,
              fetch: Optional[Callable] = None) -> bytes:
    """원문 파일을 받는다. 텍스트가 아니므로 인코딩을 건드리지 않는다.

    질의에 한글이나 공백이 들어간 파일 주소가 있어(KLI 의 fileNameOrg,
    KEIS 의 fn) 퍼센트 인코딩을 해 두지 않으면 요청 자체가 실패한다.
    """
    safe = quote(url, safe=":/?&=%#+,")
    call = fetch or _default_fetch
    last: Optional[Exception] = None
    for attempt in range(1, tries + 1):
        try:
            resp = call(safe, timeout=timeout)
            resp.raise_for_status()
            return resp.content
        except Exception as exc:       # noqa: BLE001
            last = exc
            if attempt == tries:
                break
            sleep(_backoff(attempt))
    raise last                          # type: ignore[misc]
