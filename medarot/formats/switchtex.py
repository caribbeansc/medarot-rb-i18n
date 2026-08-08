"""Work around UnityPy's Switch block-linear texture bug.

UnityPy <= 1.25.3 decides whether a Switch texture is swizzled with
``gobs_per_block > 1``, but that value is the *height of the block in GOBs*, and
Unity picks 1 for short textures. With ``gobs == 1`` the data is read: and
rewritten: as linear: scrambled blocks and a magenta band. 30 textures in this
game are affected.

``apply_fix()`` must run before the first ``UnityPy.load()`` in the process.
See ``docs/specs/SPEC-009-switch-textures.md``.
"""

from __future__ import annotations

from typing import List, Optional, Union

from UnityPy.enums import BuildTarget, TextureFormat
from UnityPy.helpers import TextureSwizzler

_APPLIED = False

#: Format ids we name in reports. 49 is ASTC_RGB_5x5, not ASTC 4x4 (48).
FORMAT_NAMES = {
    1: "Alpha8", 4: "RGBA32", 10: "DXT1", 12: "DXT5", 25: "BC7",
    48: "ASTC_RGB_4x4", 49: "ASTC_RGB_5x5", 50: "ASTC_RGB_6x6",
}


def _is_switch_swizzled_fixed(
    platform: Union[BuildTarget, int],
    platform_blob: Optional[List[int]],
) -> bool:
    """``gobs_per_block == 1`` is swizzled too."""
    if platform != BuildTarget.Switch:
        return False
    if not platform_blob or len(platform_blob) < 12:
        return False
    return TextureSwizzler.get_switch_gobs_per_block(platform_blob) >= 1


def apply_fix() -> None:
    """Patch UnityPy in memory. Idempotent; safe to call from every module."""
    global _APPLIED
    if _APPLIED:
        return
    TextureSwizzler.is_switch_swizzled = _is_switch_swizzled_fixed
    # Texture2DConverter does `from ..helpers import TextureSwizzler`, so it
    # shares the module object; reassign anyway for robustness.
    try:
        from UnityPy.export import Texture2DConverter

        Texture2DConverter.TextureSwizzler.is_switch_swizzled = _is_switch_swizzled_fixed
    except Exception:  # pragma: no cover - depends on UnityPy internals
        pass
    _APPLIED = True


def is_applied() -> bool:
    return _APPLIED


def is_affected(obj_reader, data) -> bool:
    """True if this texture would be mis-read by unpatched UnityPy."""
    blob = bytes(data.m_PlatformBlob) if data.m_PlatformBlob else b""
    if obj_reader.platform != BuildTarget.Switch or len(blob) < 12:
        return False
    return TextureSwizzler.get_switch_gobs_per_block(blob) == 1


def format_name(format_id) -> str:
    try:
        return TextureFormat(int(format_id)).name
    except ValueError:
        return FORMAT_NAMES.get(int(format_id), str(format_id))


def describe(obj_reader, data) -> dict:
    """Diagnostics for one Texture2D: format, GOBs, sizes, and whether they add up."""
    blob = bytes(data.m_PlatformBlob) if data.m_PlatformBlob else b""
    info = {
        "name": data.m_Name,
        "width": data.m_Width,
        "height": data.m_Height,
        "format": format_name(data.m_TextureFormat),
        "platform": int(obj_reader.platform),
        "gobs_per_block": None,
        "raw_size": None,
        "expected_size": None,
        "size_ok": None,
        "affected": is_affected(obj_reader, data),
    }
    if len(blob) < 12:
        return info
    gobs = TextureSwizzler.get_switch_gobs_per_block(blob)
    info["gobs_per_block"] = gobs
    try:
        block_w, block_h = TextureSwizzler.TEXTURE_FORMAT_BLOCK_SIZE_MAP[
            TextureFormat(int(data.m_TextureFormat))
        ]
    except KeyError:
        return info
    padded_w, padded_h = TextureSwizzler.get_padded_texture_size(
        data.m_Width, data.m_Height, block_w, block_h, gobs
    )
    info["padded"] = f"{padded_w}x{padded_h}"
    try:
        raw = bytes(data.get_image_data())
    except Exception:  # pragma: no cover - unreadable texture
        return info
    info["raw_size"] = len(raw)
    info["expected_size"] = (padded_w // block_w) * (padded_h // block_h) * 16
    info["size_ok"] = info["raw_size"] == info["expected_size"]
    return info


def set_image(data, img) -> None:
    """Re-inject an image keeping the texture's original format (SPEC-006/R-6)."""
    data.set_image(img, target_format=data.m_TextureFormat)
