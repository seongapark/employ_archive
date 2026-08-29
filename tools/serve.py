"""로컬 개발 서버. 배포와 동일한 조립 결과를 서빙하므로 경로가 배포와 일치한다.

실행: python -m tools.serve  (기본 8642 포트)
"""
from __future__ import annotations

import argparse
import functools
import http.server

from .build import REPO, build_site


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8642)
    args = parser.parse_args()

    out = build_site(REPO, REPO / "_site")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out))
    with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as httpd:
        print(f"serving {out} at http://127.0.0.1:{args.port}/")
        httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
