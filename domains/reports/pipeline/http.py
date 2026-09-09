"""수집기가 공유하는 얇은 네트워크 계층.

기관 사이트는 간헐적으로 502를 준다. 한 번의 일시적 실패로 그 게시판이 통째로
비지 않도록 몇 번 다시 시도한다. 인코딩을 안 알려주는 국내 사이트가 있어
utf-8 → euc-kr 순으로 본다.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from curl_cffi import requests as cf_requests


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
            sleep(2.0 * attempt)
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
