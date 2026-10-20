"""수집기가 공유하는 얇은 네트워크 계층.

기관 사이트는 간헐적으로 502를 주거나 DNS가 잠깐 실패한다(파일 CDN 리다이렉트).
한 번의 일시적 실패로 그날 수집이 통째로 비지 않도록 몇 번 다시 시도한다.
"""
from __future__ import annotations

import time
from typing import Callable, TypeVar

from curl_cffi import requests as cf_requests

T = TypeVar("T")


class Blocked(Exception):
    """사이트가 봇 차단(Cloudflare 챌린지)으로 막았다 — 주소·파싱이 고장 난 게 아니다.

    2026-10-20 www.oecd.org 가 모든 비브라우저 요청을 이렇게 막았다. 우리가 고칠 수
    없는 일이라 collect 가 실패 대신 유예(BLOCKED_GRACE_DAYS)로 다룬다.
    """


def retrying(call: Callable[[], T], *, tries: int = 3, wait: float = 2.0,
             sleep: Callable[[float], None] = time.sleep) -> T:
    for attempt in range(1, tries + 1):
        try:
            return call()
        except Exception:
            if attempt == tries:
                raise
            sleep(wait * attempt)
    raise AssertionError("unreachable")


def get(url: str, *, timeout: int = 120, tries: int = 3):
    """브라우저 지문으로 GET 한다 — 한국은행·KDI 모두 일반 클라이언트를 막는다."""
    def once():
        resp = cf_requests.get(url, impersonate="chrome", timeout=timeout)
        if resp.status_code == 403 and resp.headers.get("cf-mitigated") == "challenge":
            raise Blocked(f"봇 차단(Cloudflare 챌린지): {url}")
        resp.raise_for_status()
        return resp

    return retrying(once, tries=tries)
