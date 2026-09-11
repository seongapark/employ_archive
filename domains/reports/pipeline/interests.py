"""관심축 프로파일을 읽는다.

추천 기준은 코드가 아니라 data/interests.md 에 있다. 사람이 읽고 고치는
파일이고, 고치면 버전이 바뀌어 전체가 재판정된다.

버전은 내용에서 뽑는다 — 사람이 숫자를 올리는 걸 잊으면 프로파일이 바뀌었는데
옛 판정이 그대로 남는다.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from pydantic import BaseModel

INTERESTS_PATH = Path(__file__).resolve().parent.parent / 'data' / 'interests.md'

_AXIS = re.compile(r'^##\s+(.+?)\s*$', re.M)


class Profile(BaseModel):
    text: str
    axes: list[str]
    version: str


def load(path: Path | str | None = None) -> Profile:
    p = Path(path or INTERESTS_PATH)
    text = p.read_text(encoding='utf-8')
    # '# 닿지 않는 것' 아래의 ## 은 축이 아니다. 1단계 제목에서 끊는다.
    head = re.split(r'^#\s+닿지 않는 것\s*$', text, flags=re.M)[0]
    axes = [m.group(1).strip() for m in _AXIS.finditer(head)]
    version = hashlib.sha256(text.encode('utf-8')).hexdigest()[:8]
    return Profile(text=text, axes=axes, version=version)
