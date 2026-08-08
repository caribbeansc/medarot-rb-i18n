"""SPEC-009. Switch block-linear textures (the UnityPy swizzle bug)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from UnityPy.enums import BuildTarget
from UnityPy.helpers import TextureSwizzler

from medarot.formats import switchtex


def blob_for(block_height_log2: int) -> list[int]:
    """A platform blob whose bytes 8..12 hold the GOB height exponent."""
    return list(b"\x00" * 8 + block_height_log2.to_bytes(4, "little"))


def test_r1_fix_is_applied_and_idempotent():
    """SPEC-009/R-1."""
    switchtex.apply_fix()
    first = TextureSwizzler.is_switch_swizzled
    switchtex.apply_fix()
    assert TextureSwizzler.is_switch_swizzled is first
    assert switchtex.is_applied()


def test_r1_gobs_one_is_swizzled():
    """SPEC-009/R-1. The whole point: gobs_per_block == 1 is still swizzled."""
    switchtex.apply_fix()
    assert TextureSwizzler.is_switch_swizzled(BuildTarget.Switch, blob_for(0)) is True
    assert TextureSwizzler.is_switch_swizzled(BuildTarget.Switch, blob_for(2)) is True


def test_r2_export_path_sees_the_same_function():
    """SPEC-009/R-2: the converter's reference is patched too."""
    switchtex.apply_fix()
    from UnityPy.export import Texture2DConverter

    assert (Texture2DConverter.TextureSwizzler.is_switch_swizzled
            is TextureSwizzler.is_switch_swizzled)


@pytest.mark.parametrize("platform,blob", [
    (BuildTarget.StandaloneWindows64, blob_for(0)),
    (BuildTarget.Switch, None),
    (BuildTarget.Switch, [0] * 4),
])
def test_r3_no_op_for_other_platforms_and_short_blobs(platform, blob):
    """SPEC-009/R-3."""
    switchtex.apply_fix()
    assert TextureSwizzler.is_switch_swizzled(platform, blob) is False


def test_r4_format_49_is_astc_5x5():
    """SPEC-009/R-4: 49 is ASTC_RGB_5x5, not ASTC 4x4."""
    assert "5x5" in switchtex.format_name(49)
    assert "4x4" in switchtex.format_name(48)


def test_r4_set_image_passes_the_original_format():
    """SPEC-009/R-4: re-injection keeps the texture's own format."""
    seen = {}

    class FakeTexture:
        m_TextureFormat = 49

        def set_image(self, img, target_format=None):
            seen["format"] = target_format

    switchtex.set_image(FakeTexture(), object())
    assert seen["format"] == 49


def test_r5_is_affected_flags_only_gobs_one():
    """SPEC-009/R-5."""
    reader = SimpleNamespace(platform=BuildTarget.Switch)
    assert switchtex.is_affected(reader, SimpleNamespace(m_PlatformBlob=blob_for(0)))
    assert not switchtex.is_affected(reader, SimpleNamespace(m_PlatformBlob=blob_for(1)))
    assert not switchtex.is_affected(reader, SimpleNamespace(m_PlatformBlob=None))
    other = SimpleNamespace(platform=BuildTarget.StandaloneWindows64)
    assert not switchtex.is_affected(other, SimpleNamespace(m_PlatformBlob=blob_for(0)))


def test_r6_every_unity_using_module_goes_through_the_helper():
    """SPEC-009/R-6: nothing imports UnityPy without the fix being applied.

    The failure this guards against is invisible when extracting and only shows up
    as garbage on screen, so it is checked by scanning the source.
    """
    from pathlib import Path

    package = Path(switchtex.__file__).resolve().parent.parent
    offenders = []
    for path in sorted(package.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "import UnityPy" not in text:
            continue
        if path.name in {"unity.py", "switchtex.py"}:
            continue
        offenders.append(str(path.relative_to(package)))
    assert not offenders, (
        f"these modules import UnityPy directly instead of medarot.unity: {offenders}")


def test_unity_helper_applies_the_fix_on_import():
    from medarot import unity

    assert switchtex.is_applied()
    assert unity.packer_for("a.bundle") == unity.PACKER_BUNDLE
    assert unity.packer_for("level3") == unity.PACKER_RAW


def test_describe_handles_a_blobless_texture():
    reader = SimpleNamespace(platform=BuildTarget.Switch)
    data = SimpleNamespace(m_Name="T", m_Width=4, m_Height=4, m_TextureFormat=4,
                           m_PlatformBlob=None)
    info = switchtex.describe(reader, data)
    assert info["name"] == "T" and info["gobs_per_block"] is None


@pytest.mark.game
def test_r5_audit_finds_the_known_affected_textures(real_project):
    """SPEC-009/R-5 against the real dump: the bug does affect this game."""
    from medarot import extract

    index = extract.texture_index(real_project)
    affected = [name for name, entry in index.items() if entry.get("swizzle_bug")]
    assert affected, "expected some textures with gobs_per_block == 1"
