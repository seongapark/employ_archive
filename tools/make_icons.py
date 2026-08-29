"""PWA 아이콘 생성 스크립트.

512x512 배경(#23508f) 둥근 사각형 위에 흰색 막대그래프(3개, 높이 다르게) +
우상향 꺾은선을 그려 icon-512.png / icon-192.png 로 저장한다.

의존성: Pillow (요구사항 파일에는 추가하지 않음 — 임시로 `pip install pillow`).
실행: python tools/make_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT_DIR = Path(__file__).resolve().parent.parent / "web" / "icons"
BG_COLOR = "#23508f"
FG_COLOR = "#ffffff"
SIZE = 512


def draw_icon(size: int) -> Image.Image:
    # 4x 슈퍼샘플링 후 축소해 안티에일리어싱 품질을 확보한다.
    scale = 4
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 배경 라운드 사각형
    radius = round(s * 0.22)
    draw.rounded_rectangle([0, 0, s - 1, s - 1], radius=radius, fill=BG_COLOR)

    # 막대그래프 3개 (높이가 다름), 하단 기준선 정렬
    base_y = round(s * 0.74)
    bar_w = round(s * 0.11)
    gap = round(s * 0.07)
    heights = [0.22, 0.34, 0.46]  # size 대비 비율, 좌→우로 커짐
    total_w = bar_w * 3 + gap * 2
    start_x = round((s - total_w) / 2)

    for i, h_ratio in enumerate(heights):
        x0 = start_x + i * (bar_w + gap)
        x1 = x0 + bar_w
        bar_h = round(s * h_ratio)
        y0 = base_y - bar_h
        y1 = base_y
        draw.rounded_rectangle([x0, y0, x1, y1], radius=round(bar_w * 0.25), fill=FG_COLOR)

    # 우상향 꺾은선: 각 막대 꼭대기 중심을 지나 마지막 막대 위로 더 솟아오른다.
    bar_centers_x = [start_x + i * (bar_w + gap) + bar_w / 2 for i in range(3)]
    bar_tops_y = [base_y - round(s * h) for h in heights]
    line_pts = [
        (bar_centers_x[0], bar_tops_y[0] - round(s * 0.03)),
        (bar_centers_x[1], bar_tops_y[1] - round(s * 0.03)),
        (bar_centers_x[2], bar_tops_y[2] - round(s * 0.03)),
        (bar_centers_x[2] + round(s * 0.06), bar_tops_y[2] - round(s * 0.14)),
    ]
    line_w = max(2, round(s * 0.022))
    draw.line(line_pts, fill=FG_COLOR, width=line_w, joint="curve")

    # 선 끝점에 작은 원(화살촉 대용 포인트)
    dot_r = round(s * 0.028)
    ex, ey = line_pts[-1]
    draw.ellipse([ex - dot_r, ey - dot_r, ex + dot_r, ey + dot_r], fill=FG_COLOR)

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    icon_512 = draw_icon(512)
    icon_512.save(OUT_DIR / "icon-512.png")

    icon_192 = icon_512.resize((192, 192), Image.LANCZOS)
    icon_192.save(OUT_DIR / "icon-192.png")

    print(f"saved: {OUT_DIR / 'icon-512.png'} ({icon_512.size[0]}x{icon_512.size[1]})")
    print(f"saved: {OUT_DIR / 'icon-192.png'} ({icon_192.size[0]}x{icon_192.size[1]})")


if __name__ == "__main__":
    main()
