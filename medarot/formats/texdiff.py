"""Texture deltas: version only what the translation adds.

Instead of storing the translated texture — which is the game's artwork — store
the difference against the original:

    <name>.png        RGBA overlay: final value of every changed pixel
    <name>.mask.png   L mask: 255 where a pixel changed

See ``docs/specs/SPEC-003-texture-delta.md``.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops

MASK_SUFFIX = ".mask.png"


def _normalize(img: Image.Image) -> Image.Image:
    """Zero the RGB of fully transparent pixels (SPEC-003/R-2)."""
    red, green, blue, alpha = img.split()
    visible = alpha.point(lambda v: 255 if v else 0)
    black = Image.new("L", img.size, 0)
    return Image.merge("RGBA", (
        Image.composite(red, black, visible),
        Image.composite(green, black, visible),
        Image.composite(blue, black, visible),
        alpha,
    ))


def make_diff(original: Image.Image, translated: Image.Image):
    """Return ``(overlay, mask, percent_changed)``."""
    before = original.convert("RGBA")
    after = translated.convert("RGBA")
    if before.size != after.size:
        after = after.resize(before.size)

    before, after = _normalize(before), _normalize(after)

    difference = ImageChops.difference(before, after)
    mask = Image.new("L", before.size, 0)
    for channel in difference.split():
        mask = ImageChops.lighter(mask, channel.point(lambda v: 255 if v else 0))

    overlay = Image.new("RGBA", before.size, (0, 0, 0, 0))
    overlay.paste(after, (0, 0), mask)

    changed = mask.histogram()[255]
    percent = 100.0 * changed / (before.width * before.height)
    return overlay, mask, percent


def apply_diff(original: Image.Image, overlay: Image.Image,
               mask: Image.Image) -> Image.Image:
    """Rebuild the translated texture from the original plus the delta."""
    base = original.convert("RGBA")
    over = overlay.convert("RGBA")
    stencil = mask.convert("L")
    if over.size != base.size:
        over = over.resize(base.size)
        stencil = stencil.resize(base.size)
    out = base.copy()
    # A binary-mask paste copies the overlay's alpha too, which is what lets a
    # pixel change *to* transparent.
    out.paste(over, (0, 0), stencil)
    return out


def mask_path(overlay_png) -> Path:
    """``foo/bar.png`` -> ``foo/bar.mask.png``"""
    path = Path(overlay_png)
    return path.with_name(path.stem + MASK_SUFFIX)


def is_mask(path) -> bool:
    return str(path).endswith(MASK_SUFFIX)


def save_diff(dest_png, overlay: Image.Image, mask: Image.Image) -> None:
    dest = Path(dest_png)
    dest.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(dest)
    mask.save(mask_path(dest))


def load_translated(original, delta_png) -> Image.Image:
    """Final texture = original + delta.

    ``original`` may be a path or an already-loaded image; the caller normally
    passes the image straight out of the user's own bundle. A delta with no mask
    beside it is treated as a full replacement image (SPEC-003/R-6).
    """
    base = original if isinstance(original, Image.Image) else Image.open(original)
    overlay = Image.open(delta_png)
    mask = mask_path(delta_png)
    if not mask.exists():
        return overlay.convert("RGBA")
    return apply_diff(base, overlay, Image.open(mask))
