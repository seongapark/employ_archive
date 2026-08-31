"""텍스트 레이어가 없는 PDF 를 이미지로 읽는다.

한국고용정보원 고용동향브리프는 InDesign 이 글자를 전부 아웃라인으로 바꿔
내보내, 콘텐츠 스트림에 텍스트 연산자가 하나도 없다. 쪽을 렌더링해 OCR 하는
수밖에 없다.

그냥 OCR 하면 숫자는 다 읽히는데 행 이름이 통째로 사라진다 — 표의 라벨이
보라 배경 위 흰 글씨라서다. 지표가 뭔지 모르는 숫자 뭉치는 쓸모가 없으므로,
그런 셀만 골라 흑백을 뒤집어 흰 바탕·검은 글자로 만든 뒤 넘긴다.
"""
from __future__ import annotations

import io

import numpy as np
from PIL import Image

# 유채색 솔리드 배경을 고르는 문턱값. 채도가 낮은 검은 본문 글자와, 밝은
# 흰 바탕을 함께 걸러낸다.
SATURATION_MIN = 25
BACKGROUND_LUMA_MAX = 200
# 반전 영역 안에서 글자와 배경을 가르는 밝기. 보라 배경은 90 안팎,
# 흰 글자는 255 다.
TEXT_LUMA_MIN = 170
# 열기 창: 얇은 글자 획을 지워 '면'만 남긴다. 헤더의 보라색 글자가
# 마스크에 딸려 들어가는 것을 막는 것이 목적이다.
OPEN_K = 15
# 닫기 창: 흰 글자가 뚫어 놓은 구멍을 메워 셀 전체를 덮는다.
CLOSE_K = 45


def boxsum(mask: np.ndarray, k: int) -> np.ndarray:
    """k×k 창의 합을 적분영상으로 구한다.

    PIL 의 MinFilter/MaxFilter 는 픽셀마다 k² 번 비교해, 400dpi A4(3308×4678)
    에서 창이 45 면 한 쪽에 수 분이 걸린다. 누적합은 창 크기와 무관하다.
    """
    radius = k // 2
    padded = np.pad(mask.astype(np.int32), radius + 1, mode="constant")
    integral = padded.cumsum(0).cumsum(1)
    height, width = mask.shape
    rows = np.arange(height)[:, None]
    cols = np.arange(width)[None, :]
    return (integral[rows + k, cols + k] - integral[rows, cols + k]
            - integral[rows + k, cols] + integral[rows, cols])


def erode(mask: np.ndarray, k: int) -> np.ndarray:
    return boxsum(mask, k) == k * k


def dilate(mask: np.ndarray, k: int) -> np.ndarray:
    return boxsum(mask, k) > 0


def solid_color_mask(img: Image.Image) -> np.ndarray:
    """유채색 솔리드 배경 영역을 True 로 준다.

    채도만 보면 헤더의 보라색 '글자'까지 들어온다. 열기로 얇은 획을 지워
    '면'만 남긴 뒤, 닫기로 흰 글자가 뚫은 구멍을 메워 셀 전체를 덮는다.
    """
    rgb = np.asarray(img.convert("RGB")).astype(np.int16)
    luma = np.asarray(img.convert("L")).astype(np.int16)
    saturation = rgb.max(axis=2) - rgb.min(axis=2)
    candidate = (saturation > SATURATION_MIN) & (luma < BACKGROUND_LUMA_MAX)
    solid = dilate(erode(candidate, OPEN_K), OPEN_K)
    return erode(dilate(solid, CLOSE_K), CLOSE_K)


def flatten(img: Image.Image) -> Image.Image:
    """색 배경 위 흰 글자를 흰 바탕 검은 글자로 뒤집는다.

    밝기를 보존한 채 반전하면 보라 배경(90)이 회색(165)이 되는데, tesseract
    의 전역 이진화가 그 회색을 글자로 잡아 셀이 통째로 검은 덩어리가 된다.
    그래서 반전 영역만 이진화한다.
    """
    luma = np.asarray(img.convert("L")).astype(np.int16)
    mask = solid_color_mask(img)
    flipped = np.where(luma > TEXT_LUMA_MIN, 0, 255)
    return Image.fromarray(np.where(mask, flipped, luma).astype(np.uint8))


def page_texts(data: bytes, pages: list[int] | None = None, *,
               dpi: int = 400, preprocess: bool = True) -> list[str]:
    """PDF 를 렌더링해 쪽 텍스트를 준다. `pages` 는 1부터 세는 쪽번호다.

    전 쪽을 고해상도로 돌리면 한 호에 몇 분이 걸린다. 부르는 쪽에서 낮은
    해상도로 후보를 좁힌 뒤 그 쪽만 다시 부르는 것을 전제로 한다.
    """
    import pypdfium2 as pdfium  # 무거운 의존성이라 실제로 읽을 때만 불러온다
    import pytesseract

    # pdf.page_texts 의 pdfplumber.open 처럼 with 로 닫는다. 안 닫으면
    # pypdfium2 가 "still open" 경고를 찍는 데서 그치지 않는다 — 15개 호
    # 백필 한 번에 수십 개(호당 ~7MB)가 GC 전까지 물려 있는다.
    with pdfium.PdfDocument(io.BytesIO(data)) as doc:
        wanted = range(1, len(doc) + 1) if pages is None else pages
        out = []
        for page_no in wanted:
            img = doc[page_no - 1].render(scale=dpi / 72).to_pil()
            if preprocess:
                img = flatten(img)
            out.append(pytesseract.image_to_string(img, lang="kor+eng", config="--psm 6"))
        return out
