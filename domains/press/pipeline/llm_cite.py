# -*- coding: utf-8 -*-
"""기사가 그 회차 보도자료를 인용했는지 LLM 이 판정한다.

규칙이 아니라 LLM 을 주 판정으로 두는 이유는 규칙이 **조용히** 틀리기 때문이다.
2026-09-08 실측에서 두 번 그랬다 — 보도자료 수치를 지문으로 쓰는 규칙이 6월분
진짜 기사 33건을 떨어뜨렸고, 소수점(`2.6%`)에서 문장이 갈려 지표와 증감이
따로 놀았다. 둘 다 예외 없이 그럴듯한 숫자를 냈다.

판정과 근거를 함께 받는다. 근거가 없으면 왜 틀렸는지 아무도 못 본다.
공급자는 `JUDGE_PROVIDER=cli` 면 구독(`claude -p`)이고, 아니면 있는 키를 쓴다
(Anthropic → OpenRouter → OpenAI) — 프롬프트와 파싱은 어느 쪽이든 같고, 요청
모양만 `payload_for` 가 맞춘다.

**논조도 같은 호출에서 받는다.** 고정 어휘표로는 못 센다는 것이 실측으로
드러났다 — 어휘표 14개('빨간불'·'한파'·'훈풍'…)는 '26.8월분 인용 73건 중
10건만 잡았고, 정작 그 회차를 이끈 「반등 16 · 호황 8 · 호조 2」는 목록에
없어 '보도자료 밖 표현'으로 흘러갔다. 그 표로 KPI 를 세웠다면 **긍정 우세인
회차를 '부정 우세'로 표시**했을 것이다. 어휘를 늘려도 「구직급여 급증」과
「가입자 급증」을 못 가른다 — 같은 낱말이 주어에 따라 뒤집힌다.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Callable, NamedTuple, Sequence

# 판정은 구독(`claude -p`)으로만 돈다. API 키로 도는 길은 2026-09-14 에
# 지웠다 — 스위치 하나가 빠지면 조용히 과금되는 구조였다. 그래서 공급자별
# 주소·모델·토큰 한도 상수와 payload_for, requests 의존이 다 같이 없어졌다.
MODEL_ANTHROPIC = "claude-opus-5"
BATCH = 20                      # 한 번에 판정할 기사 수
CLI_URL = "cli://claude"        # 센티넬 — HTTP 가 아니라 `claude -p` 를 부른다
CLI_TIMEOUT = 600               # 20건 판정이 몇 분 걸린다(reports 실측 46초/묶음)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)


# 논조 판정값. 이 셋 밖의 답은 에러다 — 모르는 값을 '중립'으로 접으면
# 모델이 딴소리를 해도 화면이 멀쩡해 보인다.
TONES = ('긍정', '부정', '중립')

# 인용의 **무게**. 「수치를 전했나」와 「그 수치가 기사의 본론인가」는 다른 질문이다.
# 실측('26.7월분 후속): 인용 31건 중 「'싼 게 비지떡' 청년 주거 엇박」처럼 주거·주식·
# 수기 기사가 도입부에 통계를 끌어다 쓴 것이 여럿 섞여 있었다. 네이버가 주는 요약에
# 실제로 수치가 있으니 인용은 맞지만, 후속 보도로 세면 「이 회차가 어디까지 번졌나」가
# 부풀어 보인다. 그래서 인용 여부와 무게를 따로 받는다.
FOCUSES = ('주제', '언급')


class Verdict(NamedTuple):
    n: int          # 기사 번호 (1부터)
    cites: bool
    why: str
    tone: str       # 긍정 | 부정 | 중립
    focus: str      # 주제 | 언급 (인용이 아니면 빈 문자열)


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

그리고 각 기사의 **논조**를 함께 판정하라. 지표가 좋고 나쁜지가 아니라
**제목·요약이 노동시장을 어떻게 그리는가**다:
- "긍정" — 나아지고 있다고 그린다. 반등·호황·회복·증가 전환·훈풍.
- "부정" — 나빠지고 있다고 그린다. 한파·감소·부진·역주행·빙하기·최악.
- "중립" — 수치만 전하거나, 좋고 나쁨이 섞여 어느 쪽도 아니다.

같은 낱말이라도 **무엇이 늘고 줄었는지**를 보라. 「구직급여 신청 급증」은
부정이고 「가입자 급증」은 긍정이다. 인용이 아닌 기사도 논조는 판정하라.

인용이라면 그 수치가 기사에서 **어떤 무게**인지도 판정하라(`focus`):
- "주제" — 이 통계를 전하는 것이 기사의 본론이다. 제목이나 첫 문단이 이 수치를
  다루고, 통계를 빼면 기사가 성립하지 않는다.
- "언급" — 다른 주제(주거·주식·수기·정책 논쟁·기업 분석)를 말하면서 이 통계를
  근거로 한두 줄 끌어다 썼을 뿐이다. 통계를 빼도 기사는 남는다.
인용이 아니면 `focus` 는 빈 문자열("")로 둬라.

각 기사마다 한 줄씩, JSON 배열로만 답하라. 다른 말을 덧붙이지 마라:
[{{"n": 1, "cites": true, "why": "8월 가입자 27만8천명 증가를 전함", "tone": "긍정", "focus": "주제"}}]

`why` 는 20자 안팎으로 짧게. 인용이 아니면 무엇을 다룬 기사인지 적어라.
`tone` 은 긍정·부정·중립 중 하나만 쓴다.
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
        if "tone" not in row:
            raise ValueError(f"tone 이 없다: {row!r}")
        tone = str(row["tone"]).strip()
        if tone not in TONES:
            raise ValueError(f"tone 이 {'·'.join(TONES)} 가 아니다({tone!r}): {row!r}")
        cites = bool(row["cites"])
        if "focus" not in row:
            raise ValueError(f"focus 가 없다: {row!r}")
        focus = str(row["focus"]).strip()
        if cites and focus not in FOCUSES:
            raise ValueError(f"focus 가 {'·'.join(FOCUSES)} 가 아니다({focus!r}): {row!r}")
        if not cites:
            focus = ''          # 인용이 아니면 무게를 따질 것이 없다
        out.append(Verdict(n, cites, str(row.get("why", "")).strip(), tone, focus))
    missing = sorted(set(range(1, n_expected + 1)) - seen)
    if missing:
        # 빠진 기사를 조용히 '인용 아님' 으로 두면 누락이 안 보인다.
        raise ValueError(f"판정이 빠진 기사가 있다: {missing}")
    return sorted(out)


def provider() -> tuple[str, str, dict] | None:
    """(url, model, headers) — **구독(`claude -p`)만 쓴다.** 못 쓰면 None.

    API 키로 도는 길은 2026-09-14 에 없앴다. 예전에는 `JUDGE_PROVIDER=cli` 가
    아니면 ANTHROPIC → OPENROUTER → OPENAI 순으로 키를 찾아 썼는데, 그 스위치
    하나가 빠지거나 오타나면 **조용히 과금 경로로 넘어간다.** 잔액이 있는 키가
    하나라도 있으면 아무도 모르게 돈이 나간다.

    그래서 키를 보는 코드를 지웠다. 순서를 바꾸거나 스위치를 더 다는 것으로는
    같은 사고가 또 난다 — 길이 있으면 언젠가 그리로 간다. 지금은 길이 없다.

    구독이 막히면(토큰 만기·한도 소진) 판정이 안 되고, 그 사실이 관리자
    화면의 도메인 현황에 뜬다. 조용히 다른 지갑으로 새지 않는다.
    """
    if os.environ.get("JUDGE_PROVIDER", "").strip().lower() != "cli":
        return None
    return (CLI_URL, _cli_model(), {})


def _cli_model() -> str:
    """`claude -p` 에 넘길 모델. Pro 요금제는 Opus 사용이 제한될 수 있으므로
    `JUDGE_CLI_MODEL` 로 갈아끼울 수 있게 둔다. provider() 와 _call_cli() 가
    **같은 값**을 봐야 어느 모델이 판정했는지가 거짓이 되지 않는다.
    """
    return os.environ.get("JUDGE_CLI_MODEL", "").strip() or MODEL_ANTHROPIC


def _call_cli(prompt: str) -> str:
    """`claude -p` 로 판정한다 — API 크레딧이 아니라 **구독 한도**를 쓴다.

    **프롬프트를 argv 가 아니라 stdin 으로 준다.** 기사 20건에 요약까지 실으면
    한 묶음이 수만 자다. 리눅스는 인자 하나가 128KiB 를 넘으면 E2BIG 이고
    윈도우는 명령줄 전체가 32,767자다 — 둘 다 묶음 크기에 따라 걸린다.
    `-p` 는 프롬프트 인자가 없으면 stdin 을 읽는다(실측).

    **자식 환경에서 API 키를 지운다.** Claude Code 의 인증 우선순위는
    `ANTHROPIC_API_KEY`(3위) > `CLAUDE_CODE_OAUTH_TOKEN`(5위) 이고,
    비대화형(`-p`)에서는 키가 있으면 **항상** 그걸 쓴다. 잔액 0 인 키가 환경에
    남아 있으면 구독으로 도는 줄 알고 크레딧 부족으로 죽는다.

    **`--bare` 를 쓰지 않는다.** 그 모드는 `CLAUDE_CODE_OAUTH_TOKEN` 을 읽지
    않아 인증이 통째로 안 된다.
    """
    env = {k: v for k, v in os.environ.items()
           if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    argv = ["claude", "-p", "--output-format", "json", "--model", _cli_model()]
    done = subprocess.run(argv, input=prompt, env=env, capture_output=True,
                          text=True, encoding="utf-8", timeout=CLI_TIMEOUT)
    if done.returncode != 0:
        # 봉투를 통째로 싣는다. 300자로 자르면 앞의 usage·session_id 만 남고
        # 정작 이유(잔액·만료·로그인 필요)가 잘린다 — 2026-09-13 reports 회차가
        # 그래서 무엇이 틀렸는지 모른 채 빨갛기만 했다.
        raise ValueError(f"claude -p 가 {done.returncode} 로 끝났다: "
                         f"{done.stdout[:2000]} {done.stderr[:500]}")
    try:
        data = json.loads(done.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"claude -p 출력이 JSON 이 아니다: "
                         f"{done.stdout[:300]}") from exc
    if data.get("is_error"):
        raise ValueError(f"claude -p 가 오류를 돌려줬다: {str(data)[:300]}")
    text = data.get("result")
    if not isinstance(text, str):
        raise ValueError(f"봉투에 result 문자열이 없다: {str(data)[:300]}")
    return text


def _call_api(prompt: str) -> str:
    got = provider()
    if got is None:
        raise RuntimeError(
            "구독 판정을 쓸 수 없다 — JUDGE_PROVIDER=cli 가 아니다. "
            "API 키로 도는 길은 없다(과금 경로를 막았다).")
    return _call_cli(prompt)


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
        out.extend(Verdict(v.n + start, v.cites, v.why, v.tone, v.focus) for v in got)
    return out
