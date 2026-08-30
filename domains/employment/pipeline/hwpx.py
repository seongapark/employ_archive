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


def _cell_text(el) -> str:
    joined = "".join(n.text or "" for n in el.iter() if _local(n.tag) == "t")
    return re.sub(r"\s+", " ", joined).strip()


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
                [_cell_text(tc) for tc in tr if _local(tc.tag) == "tc"]
                for tr in (e for e in tbl.iter() if _local(e.tag) == "tr")
            ]
            out.append(rows)
    return out
