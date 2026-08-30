"""보도자료 표의 기간 칸을 읽는다.

경활 xlsx 와 고용행정 hwpx 가 같은 관례를 쓴다 — 연평균·분기·월이 한 열에 섞이고,
월은 연도가 바뀔 때만 연도를 단다. 두 수집기에 복사하면 한쪽만 고쳐지는 날이 온다.
"""
from __future__ import annotations

import re

_MONTH_START = re.compile(r"^(\d{4})\.(\d{1,2})$")
_MONTH_ONLY = re.compile(r"^(\d{1,2})$")


def squash(text: str | None) -> str:
    """공백을 모두 지운다. 두 줄로 접힌 셀을 한 낱말로 되돌린다."""
    return re.sub(r"\s+", "", text or "")


def month_rows(rows: list[list[str]], *,
               column: int = 0) -> list[tuple[str, list[str]]]:
    """월 행만 (YYYY-MM, 행) 으로. 연평균·분기·주석은 버린다.

    첫 칸에는 연평균(단독 4자리, 예: '2025'), 분기('2025.1/4'), 월별 값이
    한 표에 섞여 있다. 월은 연도가 바뀌는 시작 행에서만 'YYYY.  M' 처럼
    연도를 달고, 그 뒤로는 숫자만 온다 — 그래서 4자리 단독 행을 연도로
    오인해 이어붙이면 월 시작 행(연도가 붙은 행)은 정규식에 안 걸려 버려지고,
    그 다음 숫자만 있는 행들은 훨씬 전에 마지막으로 봤던 연평균 연도에
    잘못 붙는다 — 다음 해로 넘어간 월이 이전 해로 주저앉는다. 빈 행은 표의
    블록 경계이므로 연도 문맥을 끊는다.
    """
    out: list[tuple[str, list[str]]] = []
    year: str | None = None
    for row in rows:
        first = squash(row[column]) if len(row) > column else ""
        if not first:
            year = None            # 빈 행은 표의 블록 경계다
            continue
        started = _MONTH_START.fullmatch(first)
        if started:
            year, month = started.group(1), int(started.group(2))
            if 1 <= month <= 12:
                out.append((f"{year}-{month:02d}", row))
            continue
        only = _MONTH_ONLY.fullmatch(first)
        if year and only:
            month = int(only.group(1))
            if 1 <= month <= 12:
                out.append((f"{year}-{month:02d}", row))
    return out
