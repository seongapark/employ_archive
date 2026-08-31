"""KOSIS 표가 아직 같은 것을 말하는지 대조한다.

화면은 출처 카드에서 KOSIS 표로 링크를 건다. 그런데 **산업·직종 분류가 개편되면
통계표 id 가 바뀐다** — 옛 표는 그 자리에 남아 갱신을 멈추거나 다른 계열을 담게
된다. 링크만 걸어두면 그 사고가 조용히 지나가고, 사용자는 보도자료와 다른 숫자를
보게 된다(이 도메인이 막으려는 바로 그 일이다).

그래서 수집할 때마다 대조한다: KOSIS 표의 최신월 값이 우리가 보도자료에서 읽은
같은 달 값과 같아야 한다. 어긋나면 시끄럽게 실패시킨다.

경활만 대조한다. 사업체노동력조사는 애초에 이 표에서 숫자를 받아오므로 자기
자신과 대조하는 셈이라 의미가 없고, 고용행정통계는 KOSIS 표를 쓰지 않는다.
"""
from __future__ import annotations

import os

import requests

KOSIS_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"

# 경활 취업자(15세 이상 전체). 2026-08-31 에 보도자료와 최근 4개월이 모두 일치함을
# 확인하고 골랐다. sources.json 의 eaps.kosis_url 이 가리키는 표와 같아야 한다.
EAPS_TABLE = {
    "orgId": "101",
    "tblId": "DT_1DA7002S",
    "itmId": "T30",        # 취업자
    "objL1": "00",         # 15세 이상 전체
}

# 천명 단위. KOSIS 와 보도자료는 같은 원자료이므로 반올림 차이만 허용한다.
TOLERANCE = 0.2


def fetch_latest(period: str, *, api_key: str | None = None,
                 get=requests.get) -> float | None:
    """KOSIS 에서 그 달의 취업자를 천명으로. 못 받으면 None."""
    key = api_key if api_key is not None else os.environ.get("KOSIS_API_KEY", "").strip()
    if not key:
        return None
    params = {
        "method": "getList", "apiKey": key, "format": "json", "jsonVD": "Y",
        "userStatsId": "", "prdSe": "M",
        "startPrdDe": period.replace("-", ""), "endPrdDe": period.replace("-", ""),
        **EAPS_TABLE,
    }
    res = get(KOSIS_URL, params=params, timeout=30)
    rows = res.json() if hasattr(res, "json") else res
    if not isinstance(rows, list) or not rows:
        return None
    value = rows[0].get("DT")
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def check(records, *, api_key: str | None = None, get=requests.get) -> str | None:
    """경활 최신월을 KOSIS 와 대조한다.

    돌려주는 값은 사람이 읽을 한 줄이거나 None(대조 못 함)이다. 어긋나면
    ValueError 를 올린다 — 링크가 다른 표를 가리키기 시작했다는 뜻이고,
    그건 조용히 넘어가면 안 되는 종류의 사고다.

    키가 없거나 KOSIS 가 죽어 있으면 실패시키지 않는다. 대조를 못 한 것과
    대조에 실패한 것은 다르다.
    """
    totals = [r for r in records if r.source == "eaps" and r.breakdown == "total"]
    if not totals:
        return None
    latest = max(totals, key=lambda r: r.period)

    remote = fetch_latest(latest.period, api_key=api_key, get=get)
    if remote is None:
        return f"대조 못 함 ({latest.period}: KOSIS 응답 없음)"

    if abs(remote - latest.value) > TOLERANCE:
        raise ValueError(
            f"KOSIS {EAPS_TABLE['tblId']} 가 보도자료와 다르다: "
            f"{latest.period} KOSIS {remote} vs 보도자료 {latest.value} — "
            f"분류 개편으로 표가 바뀌었는지 확인하고 sources.json 의 "
            f"eaps.kosis_url 을 고칠 것")
    return f"{latest.period} {remote} 일치"
