"""로컬 개발 서버. 배포와 동일한 조립 결과를 서빙하므로 경로가 배포와 일치한다.

실행: python -m tools.serve  (기본 8642 포트)
"""
from __future__ import annotations

import argparse
import functools
import http.server

from .build import REPO, build_site


class _NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    """캐시하지 않는 개발용 핸들러.

    SimpleHTTPRequestHandler 는 Cache-Control 을 보내지 않는다. 그러면 브라우저가
    휴리스틱 캐시를 적용해서, 스타일을 고치고 새로고침해도 옛 CSS 가 그대로
    보인다(실제로 다크모드를 제거한 뒤 허브가 계속 어둡게 나오는 사고가 있었다).
    개발 서버에서 캐시가 주는 이득은 없고 잃는 시간만 크므로 매 응답에서 끈다.
    """

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8642)
    args = parser.parse_args()

    out = build_site(REPO, REPO / "_site")
    handler = functools.partial(_NoCacheHandler, directory=str(out))
    with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as httpd:
        print(f"serving {out} at http://127.0.0.1:{args.port}/")
        httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
