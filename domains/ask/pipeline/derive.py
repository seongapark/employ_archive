"""실보유 3종의 capability·limit·conflict 를 고용동향 데이터에서 유도한다.

손으로 쓰지 않는 이유: segments.json 의 provided 맵이 곧 교차제한이고,
industries.json 의 provided 맵이 곧 입도 한계다. 두 벌로 관리하면 어긋난다.
"""
from __future__ import annotations

AXIS_KO = {"sex": "성", "age": "연령"}
TODAY = "2026-09-08"
EV = "저장소 domains/employment/data (수집기가 실제로 채우는 축)"


def 은는(word: str) -> str:
    """받침에 따라 `은`/`는` 을 고른다.

    f-string 에 `는` 을 고정으로 붙이면 받침 있는 이름 뒤에서 어색해진다
    ("…고용행정 통계로 본 노동시장 동향는…"). 이 문자열은 `compare().설명` →
    `카드.한계` 를 타고 **화면과 LLM 프롬프트 양쪽에** 그대로 나가므로 고쳤다.

    판정은 한글 음절의 종성으로 한다 — 한글 음절 코드는 0xAC00 부터
    (초성 × 21 + 중성) × 28 + 종성 이라, 28 로 나눈 나머지가 0 이 아니면 받침이 있다.
    마지막 글자가 한글 음절이 아니면(영문·숫자·기호) 판정할 근거가 없으므로
    `는` 으로 둔다 — 지금 카탈로그의 이름은 전부 한글로 끝난다.
    """
    s = str(word or "")
    if not s:
        return "는"
    last = s[-1]
    if not ("가" <= last <= "힣"):
        return "는"
    return "은" if (ord(last) - 0xAC00) % 28 else "는"


def derive_capabilities(segments, industries, sources):
    codes = [s["code"] for s in sources]
    axes = {c: [] for c in codes}
    limits = []

    for c in codes:
        if any(i["provided"].get(c) for i in industries):
            axes[c].append("산업")

    for seg in segments:
        ko = AXIS_KO[seg["breakdown"]]
        for c in codes:
            has = any(cat["provided"].get(c) for cat in seg["categories"])
            if has:
                axes[c].append(ko)
            else:
                limits.append({
                    "id": f"LIM-{c}-교차제한-{seg['breakdown']}",
                    "source_id": c, "유형": "교차제한", "axis": ko, "category": None,
                    "내용": f"{ko}별을 발표하지 않는다",
                    "사유": "공표표 없음",
                    "evidence": EV, "verified_at": TODAY, "evidence_status": "확인"})

    for c in codes:
        missing = [i for i in industries if not i["provided"].get(c)]
        for i in missing:
            limits.append({
                "id": f"LIM-{c}-입도-{i['code']}",
                "source_id": c, "유형": "입도", "axis": "산업", "category": i["code"],
                "내용": f"산업 {i['code']}({i['short_ko']}) 미제공",
                "사유": "해당 산업을 발표하지 않는다",
                "evidence": EV, "verified_at": TODAY, "evidence_status": "확인"})

    by = {s["code"]: s for s in sources}
    caps = [{
        "source_id": c,
        "주제": [by[c]["headline_ko"]],
        "집단축": axes[c],
        "지역입도": ["전국"],
        "시간입도": ["월"],
        "기간_from": None, "기간_to": None,
        "공표시차": by[c]["release_rule"],
        "evidence": EV, "verified_at": TODAY, "evidence_status": "확인",
    } for c in codes]

    for c in codes:
        limits.append({
            "id": f"LIM-{c}-커버리지", "source_id": c, "유형": "커버리지",
            "axis": None, "category": None,
            "내용": by[c]["coverage"], "사유": by[c]["caveat"],
            "evidence": EV, "verified_at": TODAY, "evidence_status": "확인"})

    return caps, limits


def derive_conflicts(sources):
    by = {s["code"]: s for s in sources}
    rows = []
    for a, b in [("eaps", "est"), ("eaps", "ei"), ("est", "ei")]:
        rows.append({
            "id": f"CONF-{a}-{b}-개념", "source_a": a, "source_b": b,
            "차이유형": "개념",
            "설명": f"{by[a]['name_ko']}{은는(by[a]['name_ko'])} {by[a]['headline_ko']}, "
                    f"{by[b]['name_ko']}{은는(by[b]['name_ko'])} {by[b]['headline_ko']}로 "
                    f"개념이 다르다",
            "비교가능": "증감률만",
            "evidence": EV, "verified_at": TODAY, "evidence_status": "확인"})
        rows.append({
            "id": f"CONF-{a}-{b}-모집단", "source_a": a, "source_b": b,
            "차이유형": "모집단",
            "설명": f"{by[a]['coverage']} vs {by[b]['coverage']}",
            "비교가능": "증감률만",
            "evidence": EV, "verified_at": TODAY, "evidence_status": "확인"})
    return rows
