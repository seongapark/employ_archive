"""hwpx 문서의 표를 문자열 격자로 읽는다.

hwpx 는 ZIP + XML 이므로 표준 라이브러리로 충분하다. 표는
<hp:tbl> → <hp:tr> → <hp:tc> 이고 텍스트는 <hp:t> 에 들어 있다.
"""
from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET

_SECTION = re.compile(r"^Contents/section(\d+)\.xml$")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _iter_own(el, want: str):
    """el 아래에서 want 태그를 찾되, 중첩된 tbl 안으로는 내려가지 않는다.

    .iter() 는 서브트리 전체를 훑어 중첩 표의 행까지 바깥 표에 딸려온다.
    중첩 표는 root.iter() 가 자기 항목으로 따로 내놓으므로, 여기서 또 가져가면
    흡수와 중복이 동시에 일어난다.
    """
    for child in el:
        name = _local(child.tag)
        if name == "tbl":
            continue
        if name == want:
            yield child
        else:
            yield from _iter_own(child, want)


def _cell_text(el) -> str:
    """셀 텍스트. 문단 사이에는 공백을 넣는다 — 붙이면 값이 뭉개진다.

    문단(p)·텍스트(t) 수집 모두 _iter_own 을 써서 중첩 표 안으로 내려가지
    않는다 — 그러지 않으면 문단 구조가 없는 셀(폴백 경로)에서 중첩 표의
    텍스트까지 딸려온다.
    """
    paragraphs = []
    for p in _iter_own(el, "p"):
        text = "".join(t.text or "" for t in _iter_own(p, "t"))
        if text.strip():
            paragraphs.append(text.strip())
    if not paragraphs:
        # 문단 구조가 없는 셀은 예전처럼 통째로 긁는다 (중첩 표는 제외)
        paragraphs = ["".join(t.text or "" for t in _iter_own(el, "t"))]
    return re.sub(r"\s+", " ", " ".join(paragraphs)).strip()


def tables(data: bytes) -> list[list[list[str]]]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        # 섹션이 여러 개일 수 있다. 경활 보도자료는 section0~2 이고 본문 표가
        # section2 에 있다 — section0 만 읽으면 표지만 나온다.
        # 번호로 정렬한다. 문자열 정렬은 section10 을 section2 앞에 놓는다.
        sections = sorted(
            (int(m.group(1)), n)
            for n in z.namelist() if (m := _SECTION.match(n))
        )
        payloads = [z.read(n) for _, n in sections]

    out: list[list[list[str]]] = []
    for payload in payloads:
        root = ET.fromstring(payload)
        for tbl in (e for e in root.iter() if _local(e.tag) == "tbl"):
            rows = [
                [_cell_text(tc) for tc in _iter_own(tr, "tc")]
                for tr in _iter_own(tbl, "tr")
            ]
            out.append(rows)
    return out
