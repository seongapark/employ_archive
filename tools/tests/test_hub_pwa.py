"""허브를 앱으로 설치할 수 있는가.

크롬이 '앱 설치' 를 권하려면 **manifest 와 서비스워커가 둘 다** 있어야 한다.
하나만 있으면 '홈 화면에 바로가기' 로 떨어지고, 사용자는 설치했다고 생각하는데
앱이 아닌 것을 갖게 된다(2026-09-10 에 실제로 그렇게 헷갈렸다).

그리고 이 자리의 `sw.js` 는 **옛 루트 워커를 폐기하는 역할**을 겸한다 —
리팩터 전 배포본이 전망 앱 워커를 스코프 '/' 로 여기 등록해 두었기 때문이다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

HUB = Path(__file__).resolve().parents[2] / "hub"


def sw_text() -> str:
    return (HUB / "sw.js").read_text(encoding="utf-8")


def shell_assets() -> list[str]:
    return re.findall(r"'\./([^']*)'", sw_text().split("];")[0])


def test_the_hub_has_both_a_manifest_and_a_service_worker():
    # 둘 중 하나만 있으면 설치 배너가 안 뜬다.
    assert (HUB / "manifest.webmanifest").is_file()
    assert (HUB / "sw.js").is_file()
    html = (HUB / "index.html").read_text(encoding="utf-8")
    assert 'rel="manifest"' in html, "index.html 이 manifest 를 안 건다"
    assert "serviceWorker" in html, "index.html 이 서비스워커를 등록하지 않는다"


def test_the_manifest_has_what_chrome_requires():
    m = json.loads((HUB / "manifest.webmanifest").read_text(encoding="utf-8"))
    for key in ("name", "short_name", "start_url", "display", "icons"):
        assert m.get(key), key
    assert m["display"] == "standalone", "바로가기가 아니라 앱으로 열려야 한다"
    크기 = {i["sizes"] for i in m["icons"]}
    # 크롬은 192·512 를 요구한다. 하나라도 없으면 설치 대상이 아니다.
    assert {"192x192", "512x512"} <= 크기, 크기


def test_every_manifest_icon_exists():
    m = json.loads((HUB / "manifest.webmanifest").read_text(encoding="utf-8"))
    for i in m["icons"]:
        assert (HUB / i["src"].lstrip("./")).is_file(), i["src"]


def test_every_shell_asset_exists():
    # 없는 파일이 목록에 있으면 cache.addAll 이 통째로 거부돼 설치가 실패한다.
    repo = HUB.parent
    for rel in shell_assets():
        if rel in ("", "index.html"):
            continue
        base = repo if rel.startswith("core/") else HUB
        assert (base / rel).is_file(), f"앱 셸 목록에 없는 파일이 있다: {rel}"


def test_the_worker_never_deletes_another_apps_cache():
    # 처음엔 자기 것 말고 전부 지웠다. 브라우저로 보니 도메인 앱 캐시(ask-v1 등)가
    # 매번 날아갔다 — 허브를 한 번 열 때마다 다섯 앱의 오프라인 지원이 사라진다.
    t = sw_text()
    assert "startsWith('hub-')" in t, '우리 것만 지우는 가드가 사라졌다'
    지운범위 = t.split('caches.keys()')[1].split('clients.claim')[0]
    assert 'hub-' in 지운범위, '자기 것 말고 전부 지우면 남의 앱 캐시까지 날아간다'
    assert 'caches.delete' in t, '옛 버전 캐시를 정리하는 경로는 남아 있어야 한다'


def test_the_worker_leaves_domain_apps_alone():
    # 스코프가 사이트 전체라, 남의 파일까지 캐시하면 옛 사고가 되풀이된다.
    assert "허브것" in sw_text()
