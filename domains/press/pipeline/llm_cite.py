# -*- coding: utf-8 -*-
"""기사가 그 회차 보도자료를 인용했는지 LLM 이 판정한다.

규칙이 아니라 LLM 을 주 판정으로 두는 이유는 규칙이 **조용히** 틀리기 때문이다.
2026-09-08 실측에서 두 번 그랬다 — 보도자료 수치를 지문으로 쓰는 규칙이 6월분
진짜 기사 33건을 떨어뜨렸고, 소수점(`2.6%`)에서 문장이 갈려 지표와 증감이
따로 놀았다. 둘 다 예외 없이 그럴듯한 숫자를 냈다.

판정과 근거를 함께 받는다. 근거가 없으면 왜 틀렸는지 아무도 못 본다.
공급자는 둘 중 있는 키를 쓴다 — 판정 로직은 어느 쪽이든 같다.
"""
from __future__ import annotations

import json
import os
import re
from typing import Callable, NamedTuple, Sequence

import requests

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL_ANTHROPIC = "claude-opus-5"
MODEL_OPENROUTER = "anthropic/claude-opus-5"
MAX_TOKENS = 4000
TIMEOUT = 180
BATCH = 20                      # 한 번에 판정할 기사 수

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)


class Verdict(NamedTuple):
    n: int          # 기사 번호 (1부터)
    cites: bool
    why: str


def build_prompt(release_label: str, release_date: str, digest: str,
                 arts: Sequence[dict]) -> str:
    lines = []
    for i, a in enumerate(arts, start=1):
        desc = re.sub(r"\s+", " ", a.get("desc", ""))[:200]
        lines.append(f'{i}. [{a.get("press","")}] {a["title"]}\n   {desc}')
    listing = "\n".join(lines)
    return f"""고용노동부가 {release_date} 에 「{release_label}」 보도자료를 냈다.

그 보도자료의 요지:
{digest}

아래는 그 무렵 나온 기사들이다. 각 기사가 **이 보도자료가 발표한 통계를 전한
기사인지** 판정하라.

판정 기준:
- 이 보도자료의 수치·증감을 전하면 인용이다. 출처를 안 밝혀도 인용이다
  (수치만 받아쓰는 기사가 많다).
- 같은 낱말(고용보험·구직급여)을 써도 **다른 것을 말하면 인용이 아니다** —
  제도 개편, 법률 해설, 국회 심의, 개인 수기, 다른 기관의 조사, 지자체 사업.
- 여러 보도자료를 묶은 헤드라인 모음·[오늘의 신문] 류는 인용이 아니다.
- 애매하면 인용이 아닌 쪽으로 판정하라. 다만 그 이유를 적어라.

기사 목록:
{listing}

각 기사마다 한 줄씩, JSON 배열로만 답하라. 다른 말을 덧붙이지 마라:
[{{"n": 1, "cites": true, "why": "8월 가입자 27만8천명 증가를 전함"}}]

`why` 는 20자 안팎으로 짧게. 인용이 아니면 무엇을 다룬 기사인지 적어라.
"""


def parse_response(body: str, n_expected: int) -> list[Verdict]:
    """JSON 배열을 읽는다. 못 읽으면 ValueError — 조용히 넘기지 않는다."""
    text = body.strip()
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    try:
        rows = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"응답을 JSON 으로 읽지 못했다: {body[:200]}") from exc
    if not isinstance(rows, list):
        raise ValueError(f"배열이 아니다: {body[:200]}")
    out, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"항목이 객체가 아니다: {row!r}")
        try:
            n = int(row["n"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"n 을 읽지 못했다: {row!r}") from exc
        if not (1 <= n <= n_expected):
            raise ValueError(f"n 이 범위 밖이다({n}, 1~{n_expected}): {row!r}")
        if n in seen:
            raise ValueError(f"n 이 중복이다: {n}")
        seen.add(n)
        if "cites" not in row:
            raise ValueError(f"cites 가 없다: {row!r}")
        out.append(Verdict(n, bool(row["cites"]), str(row.get("why", "")).strip()))
    missing = sorted(set(range(1, n_expected + 1)) - seen)
    if missing:
        # 빠진 기사를 조용히 '인용 아님' 으로 두면 누락이 안 보인다.
        raise ValueError(f"판정이 빠진 기사가 있다: {missing}")
    return sorted(out)


def provider() -> tuple[str, str, dict] | None:
    """(url, model, headers) — 있는 키를 쓴다. 없으면 None (호출자가 규칙으로 간다)."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return (ANTHROPIC_URL, MODEL_ANTHROPIC,
                {"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return (OPENROUTER_URL, MODEL_OPENROUTER,
                {"Authorization": f"Bearer {key}", "content-type": "application/json"})
    return None


def _call_api(prompt: str) -> str:
    got = provider()
    if got is None:
        raise RuntimeError("ANTHROPIC_API_KEY 도 OPENROUTER_API_KEY 도 없다")
    url, model, headers = got
    if "anthropic.com" in url:
        payload = {"model": model, "max_tokens": MAX_TOKENS,
                   "messages": [{"role": "user", "content": prompt}]}
    else:
        payload = {"model": model, "max_tokens": MAX_TOKENS,
                   "messages": [{"role": "user", "content": prompt}]}
    resp = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
    if resp.status_code != 200:
        raise ValueError(f"API 가 {resp.status_code} 를 돌려줬다: {resp.text[:300]}")
    data = resp.json()
    try:
        if "content" in data:                       # Anthropic Messages
            return "".join(b.get("text", "") for b in data["content"])
        return data["choices"][0]["message"]["content"]   # OpenAI 호환
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ValueError(f"200 응답인데 형식이 예상과 다르다: {resp.text[:300]}") from exc


def judge(release_label: str, release_date: str, digest: str, arts: Sequence[dict],
          *, call: Callable[[str], str] | None = None,
          log: Callable[[str], None] = print) -> list[Verdict]:
    """기사 전체를 BATCH 씩 나눠 판정한다. 번호는 전체 기준으로 돌려준다."""
    call = call or _call_api
    out = []
    for start in range(0, len(arts), BATCH):
        chunk = list(arts[start:start + BATCH])
        log(f"  판정 {start + 1}~{start + len(chunk)} / {len(arts)}")
        got = parse_response(
            call(build_prompt(release_label, release_date, digest, chunk)), len(chunk))
        out.extend(Verdict(v.n + start, v.cites, v.why) for v in got)
    return out
