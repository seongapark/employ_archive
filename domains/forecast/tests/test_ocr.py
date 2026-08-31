import numpy as np
import pytest
from PIL import Image, ImageFilter

from domains.forecast.pipeline import ocr


def _pil_erode(mask, k):
    """PIL 랭크 필터로 구한 침식 — 적분영상 구현의 대조군."""
    img = Image.fromarray((mask * 255).astype("uint8"))
    return np.asarray(img.filter(ImageFilter.MinFilter(k))) > 0


def _pil_dilate(mask, k):
    img = Image.fromarray((mask * 255).astype("uint8"))
    return np.asarray(img.filter(ImageFilter.MaxFilter(k))) > 0


def _interior(a, k):
    # PIL 은 가장자리를 복제해 패딩하고 적분영상은 0 으로 패딩한다.
    # 테두리 k 픽셀은 정의가 다르므로 안쪽만 대조한다.
    return a[k:-k, k:-k]


def test_erode_matches_pil_rank_filter():
    rng = np.random.default_rng(0)
    mask = rng.random((60, 80)) > 0.5
    assert (_interior(ocr.erode(mask, 5), 5)
            == _interior(_pil_erode(mask, 5), 5)).all()


def test_dilate_matches_pil_rank_filter():
    rng = np.random.default_rng(1)
    mask = rng.random((60, 80)) > 0.5
    assert (_interior(ocr.dilate(mask, 5), 5)
            == _interior(_pil_dilate(mask, 5), 5)).all()


PURPLE = (107, 91, 154)


def _canvas(size=(400, 300)):
    return Image.new("RGB", size, "white")


def test_solid_color_cell_enters_the_mask():
    img = _canvas()
    img.paste(PURPLE, (50, 50, 350, 120))          # 보라 셀
    mask = ocr.solid_color_mask(img)
    assert mask[85, 200]                            # 셀 한가운데


def test_black_text_on_white_stays_outside_the_mask():
    img = _canvas()
    img.paste((0, 0, 0), (50, 200, 56, 230))        # 얇은 검은 획
    mask = ocr.solid_color_mask(img)
    assert not mask[215, 53]


def test_thin_colored_glyphs_are_opened_away():
    # 헤더의 보라색 글자('2023년')는 획이 얇다. 열기가 지워 주지 않으면
    # 마스크에 들어가 반전돼 버린다.
    img = _canvas()
    img.paste(PURPLE, (50, 200, 58, 240))           # 폭 8px 획
    mask = ocr.solid_color_mask(img)
    assert not mask[220, 54]


def test_flatten_inverts_white_text_on_the_cell_only():
    img = _canvas()
    img.paste(PURPLE, (50, 50, 350, 120))
    # 구멍이 닫기 창(CLOSE_K=45)보다 커지면 메워지지 않는다 — 작게 둔다
    img.paste((255, 255, 255), (100, 70, 120, 90))   # 셀 안 흰 글자
    img.paste((0, 0, 0), (100, 200, 140, 230))       # 셀 밖 검은 글자
    out = np.asarray(ocr.flatten(img))
    assert out[80, 110] == 0        # 흰 글자 -> 검정
    assert out[85, 300] == 255      # 보라 배경 -> 흰색
    assert out[215, 120] == 0       # 셀 밖 검은 글자는 그대로 검정
    assert out[215, 300] == 255     # 셀 밖 흰 바탕은 그대로 흰색
