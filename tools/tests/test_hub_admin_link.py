"""허브에서 관리자(방문 현황)로 가는 문이 살아 있는지 지킨다.

이 링크가 이 기능의 **유일한 진입점**이다. 처음 만들었을 때 화면과 잠금은 다
돌았는데 링크가 없어서, 주소를 외운 사람만 들어갈 수 있었다. 지우면 같은 일이
조용히 반복된다 — 관리자 화면은 허브 카드 목록(`hub/js/state.js` 의 `DOMAINS`)에
없으므로 다른 어떤 경로로도 안 드러난다.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
HUB = REPO / "hub" / "index.html"
ADMIN = REPO / "domains" / "admin" / "app" / "index.html"


def hub_html() -> str:
    return HUB.read_text(encoding="utf-8")


def test_hub_links_to_admin():
    assert './admin/' in hub_html(), "허브에 관리자로 가는 링크가 없다 — 주소를 아는 사람만 들어간다"


def test_the_admin_app_the_link_points_at_exists():
    # 링크만 있고 앱이 없으면 404 다. 빌드가 domains/*/app 을 그대로 복사하므로
    # 이 파일이 있으면 배포본의 /admin/ 도 있다.
    assert ADMIN.is_file(), "허브가 가리키는 관리자 앱이 없다"


def test_the_admin_door_is_reachable_without_javascript():
    # 톱니를 <button> 으로 바꾸고 hub.js 에 이동을 맡기면, 스크립트가 실패한 순간
    # 문이 사라진다. 헤더 안에 <a href="./admin/"> 로 있어야 한다.
    html = hub_html()
    header = html.split("<header", 1)[1].split("</header>", 1)[0]
    assert 'href="./admin/"' in header, "관리자 문이 헤더 안의 링크가 아니다"


def test_the_admin_page_does_not_carry_the_beacon():
    # 관리자 화면 방문이 통계에 섞이면 본인 제외 스위치가 무의미해진다.
    # 허브에 문을 낸 김에 실수로 비콘까지 붙이지 않았는지 함께 지킨다.
    assert "data-track-domain" not in ADMIN.read_text(encoding="utf-8"), (
        "관리자 화면에 비콘이 붙었다 — 자기 방문이 통계에 섞인다")
