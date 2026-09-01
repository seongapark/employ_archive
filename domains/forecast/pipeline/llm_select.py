"""보고서 전문을 주고 지표별 근거 문장을 지목하게 한다.

요약시키지 않는다. 원문 문장을 그대로 옮기게 하고, 옮긴 것이 맞는지는
llm_verify 가 따로 대조한다 — 이 모듈은 검증을 모른다.

쪽을 좁히지 않고 전문을 주는 것이 규칙 방식과의 가장 큰 차이다. 규칙 방식은
표 앞뒤 한 쪽씩만 봤는데, 창을 넓히자 한국은행 집필진 명단이 근거로 뽑혔다
(낱말만 보면 조건을 다 만족한다). LLM 은 그것을 근거로 착각하지 않으므로
BOK 의 진짜 서술이 8·10·11·39·43쪽에 흩어져 있어도 닿는다.
"""
from __future__ import annotations

import json
import os
import re
from typing import Callable, NamedTuple, Sequence

import requests

MODEL = "claude-sonnet-5"
API_URL = "https://api.anthropic.com/v1/messages"
MAX_TOKENS = 2000
TIMEOUT = 120

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)


class Picked(NamedTuple):
    indicator: str
    text: str
    source_page: int


def build_prompt(org: str, title: str, indicators: Sequence[str],
                 pages: Sequence[str]) -> str:
    body = "\n\n".join(f"[{n}쪽]\n{t}" for n, t in enumerate(pages, start=1))
    wanted = ", ".join(indicators)
    return f"""다음은 {org} 의 「{title}」 전문이다.

지표마다 **그 전망을 그렇게 한 이유를 말하는 문장 하나**를 원문에서 찾아라.

대상 지표: {wanted}

규칙:
- 원문을 **한 글자도** 바꾸지 마라. 다듬거나 요약하면 버려진다.
- 이유를 말하는 문장이 없으면 그 지표는 **비워라.** 빈 칸은 정상이고
  지어낸 근거보다 낫다.
- 수치를 다시 말하는 문장은 근거가 아니다("3.2% 성장할 전망" 은 전망이지
  이유가 아니다).
- 표·목차·집필진 명단·각주·참고문헌은 근거가 아니다.
- 그 문장이 실린 쪽번호를 함께 적어라.

JSON 배열로만 답하라. 다른 말을 덧붙이지 마라:
[{{"indicator": "...", "text": "...", "source_page": 1}}]

{body}
"""


def parse_response(body: str) -> list[Picked]:
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
    out = []
    for row in rows:
        text_ = str(row.get("text", "")).strip()
        if not text_:
            continue  # 근거 없음은 정상이다
        out.append(Picked(str(row["indicator"]), text_, int(row["source_page"])))
    return out


def _call_api(prompt: str) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY 가 없다")
    resp = requests.post(
        API_URL,
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": MODEL, "max_tokens": MAX_TOKENS,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return "".join(b.get("text", "") for b in resp.json()["content"])


def select(org: str, title: str, indicators: Sequence[str], pages: Sequence[str],
           *, call: Callable[[str], str] | None = None) -> list[Picked]:
    call = call or _call_api
    return parse_response(call(build_prompt(org, title, indicators, pages)))
