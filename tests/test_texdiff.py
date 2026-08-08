"""SPEC-003: texture translation delta."""

from __future__ import annotations

from PIL import Image

from medarot.formats import texdiff


def solid(colour, size=(8, 8)) -> Image.Image:
    return Image.new("RGBA", size, colour)


def test_r1_overlay_shape_and_transparency():
    """SPEC-003/R-1: overlay is RGBA, same size, transparent outside the mask."""
    before = solid((10, 20, 30, 255))
    after = before.copy()
    after.putpixel((1, 1), (255, 0, 0, 255))

    overlay, mask, percent = texdiff.make_diff(before, after)
    assert overlay.mode == "RGBA" and overlay.size == before.size
    assert overlay.getpixel((1, 1)) == (255, 0, 0, 255)
    assert overlay.getpixel((0, 0)) == (0, 0, 0, 0)
    assert mask.getpixel((1, 1)) == 255 and mask.getpixel((0, 0)) == 0
    assert percent == 100.0 / 64


def test_r2_alpha_only_change_is_detected():
    """SPEC-003/R-2: a change in alpha alone counts."""
    before = solid((10, 20, 30, 255))
    after = before.copy()
    after.putpixel((2, 2), (10, 20, 30, 0))
    _, mask, _ = texdiff.make_diff(before, after)
    assert mask.getpixel((2, 2)) == 255


def test_r2_rgb_under_full_transparency_is_ignored():
    """SPEC-003/R-2: two fully transparent pixels are equal whatever their RGB."""
    before = solid((0, 0, 0, 0))
    after = solid((255, 0, 255, 0))
    _, mask, percent = texdiff.make_diff(before, after)
    assert percent == 0.0
    assert mask.getbbox() is None


def test_r3_apply_reproduces_the_translation_exactly():
    """SPEC-003/R-3: original + delta == translated, alpha included."""
    before = Image.new("RGBA", (6, 6), (0, 0, 0, 0))
    for x in range(6):
        before.putpixel((x, 0), (x * 40, 10, 20, 255))
    after = before.copy()
    after.putpixel((0, 0), (0, 0, 0, 0))            # erased to transparent
    after.putpixel((3, 3), (255, 255, 255, 128))    # new semi-transparent pixel

    overlay, mask, _ = texdiff.make_diff(before, after)
    rebuilt = texdiff.apply_diff(before, overlay, mask)
    assert list(rebuilt.getdata()) == list(after.getdata())


def test_r4_no_change_means_empty_delta():
    """SPEC-003/R-4."""
    before = solid((1, 2, 3, 255))
    overlay, mask, percent = texdiff.make_diff(before, before.copy())
    assert percent == 0.0
    assert mask.getbbox() is None
    assert overlay.getbbox() is None


def test_r5_mask_filename(tmp_path):
    """SPEC-003/R-5."""
    assert texdiff.mask_path("a/b/Card.png").name == "Card.mask.png"
    assert texdiff.is_mask("x/Card.mask.png")
    assert not texdiff.is_mask("x/Card.png")


def test_r6_overlay_without_mask_is_a_full_image(tmp_path):
    """SPEC-003/R-6: legacy full-image deltas still work."""
    full = solid((9, 9, 9, 255))
    path = tmp_path / "Card.png"
    full.save(path)
    out = texdiff.load_translated(solid((0, 0, 0, 255)), path)
    assert out.getpixel((0, 0)) == (9, 9, 9, 255)


def test_r7_delta_is_resized_not_cropped(tmp_path):
    """SPEC-003/R-7."""
    before = solid((0, 0, 0, 255), size=(4, 4))
    after = solid((255, 255, 255, 255), size=(4, 4))
    overlay, mask, _ = texdiff.make_diff(before, after)
    bigger = solid((0, 0, 0, 255), size=(8, 8))
    out = texdiff.apply_diff(bigger, overlay, mask)
    assert out.size == (8, 8)
    assert out.getpixel((7, 7)) == (255, 255, 255, 255)


def test_save_and_load_roundtrip(tmp_path):
    before = solid((5, 5, 5, 255))
    after = before.copy()
    after.putpixel((4, 4), (7, 8, 9, 255))
    overlay, mask, _ = texdiff.make_diff(before, after)
    dest = tmp_path / "sub" / "Card.png"
    texdiff.save_diff(dest, overlay, mask)
    assert dest.exists() and texdiff.mask_path(dest).exists()
    rebuilt = texdiff.load_translated(before, dest)
    assert list(rebuilt.getdata()) == list(after.getdata())


def test_make_diff_resizes_mismatched_input():
    before = solid((0, 0, 0, 255), size=(4, 4))
    after = solid((255, 255, 255, 255), size=(8, 8))
    overlay, _, percent = texdiff.make_diff(before, after)
    assert overlay.size == (4, 4)
    assert percent == 100.0
