"""xlsx 를 문자열 격자로 읽는다.

openpyxl 을 쓰지 않는 이유는 의존성을 늘리지 않기 위해서다. xlsx 는 ZIP 안의
XML 이고 우리가 필요한 것은 시트 하나를 격자로 읽는 것뿐이다.
"""
from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"m": NS_MAIN, "r": NS_REL}

_CELL_REF = re.compile(r"^([A-Z]+)(\d+)$")


def _col_index(ref: str) -> int:
    """'A1' -> 0, 'B3' -> 1, 'AA12' -> 26."""
    m = _CELL_REF.match(ref)
    if m is None:
        # 여기서 조용히 넘어가면 좌표 배치가 순진한 append 로 퇴화한다 —
        # 이 모듈이 존재하는 이유인 그 결함이다.
        raise ValueError(f"셀 참조를 읽을 수 없다: {ref!r}")
    n = 0
    for ch in m.group(1):
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n - 1


def _shared_strings(z: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter(f"{{{NS_MAIN}}}t"))
            for si in root.findall("m:si", NS)]


def _sheet_paths(z: zipfile.ZipFile) -> dict[str, str]:
    rels = {r.get("Id"): r.get("Target")
            for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    paths = {}
    for sh in ET.fromstring(z.read("xl/workbook.xml")).find("m:sheets", NS):
        target = rels[sh.get(f"{{{NS_REL}}}id")].lstrip("/")
        paths[sh.get("name")] = target if target.startswith("xl/") else "xl/" + target
    return paths


def sheet_names(data: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return list(_sheet_paths(z))


def read_sheet(data: bytes, name: str) -> list[list[str]]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        paths = _sheet_paths(z)
        if name not in paths:
            raise KeyError(f"시트가 없다: {name!r}")
        sst = _shared_strings(z)
        root = ET.fromstring(z.read(paths[name]))

    rows: list[list[str]] = []
    for row in root.iter(f"{{{NS_MAIN}}}row"):
        cells: list[str] = []
        for c in row.findall("m:c", NS):
            # 빈 셀은 생략되므로 좌표로 자리를 맞춘다. 순서대로 이어붙이면
            # 빈 칸만큼 열이 밀려 산업이 통째로 어긋난다.
            idx = _col_index(c.get("r") or "")
            while len(cells) < idx:
                cells.append("")
            if c.get("t") == "inlineStr":
                raise ValueError("inlineStr 셀은 아직 지원하지 않는다")
            v = c.find("m:v", NS)
            if v is None or v.text is None:
                cells.append("")
            elif c.get("t") == "s":
                cells.append(sst[int(v.text)])
            else:
                cells.append(v.text)
        rows.append(cells)
    return rows
