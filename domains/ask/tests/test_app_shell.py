"""서비스워커의 앱 셸 목록이 실제 파일과 맞는가.

없는 파일이 목록에 있으면 `cache.addAll` 이 통째로 거부돼 **설치가 실패한다** —
그러면 오프라인 지원이 조용히 사라진다. 반대로 화면이 쓰는 파일이 목록에 없으면
온라인에서는 멀쩡한데 오프라인에서만 깨진다(2026-09-10 에 실제로 그랬다:
화면을 `render.js` 에서 `lookup.js` 로 옮기고 목록을 안 고쳤다).
"""
from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"
REPO = Path(__file__).resolve().parents[3]


def shell_assets() -> list[str]:
    text = (APP / "sw.js").read_text(encoding="utf-8")
    head = text.split("];")[0]
    return re.findall(r"'\./([^']*)'", head)


def resolve(rel: str) -> Path:
    # 빌드가 저장소 `core/` 를 각 앱 아래로 복사한다 — 앱 폴더에는 없다.
    if rel.startswith("core/"):
        return REPO / rel
    return APP / rel


def test_every_shell_asset_exists():
    for rel in shell_assets():
        if rel in ("", "index.html"):
            continue
        assert resolve(rel).exists(), f"앱 셸 목록에 없는 파일이 있다: {rel}"


def test_every_script_the_page_loads_is_in_the_shell():
    html = (APP / "index.html").read_text(encoding="utf-8")
    쓰는것 = set(re.findall(r'src="\./(js/[^"]+)"', html))
    목록 = set(shell_assets())
    빠진것 = 쓰는것 - 목록
    assert not 빠진것, f"화면이 쓰는데 앱 셸에 없다: {sorted(빠진것)}"


def test_the_shell_does_not_list_scripts_nobody_imports():
    # 안 쓰는 파일이 목록에 남아 있으면 지운 날 설치가 실패한다.
    js = {p.name for p in (APP / "js").glob("*.js")}
    for rel in shell_assets():
        if rel.startswith("js/"):
            assert rel.split("/")[-1] in js, f"앱 셸이 없는 스크립트를 가리킨다: {rel}"
