"""SPEC-003/R-8, R-9 — importing edited artwork, and the texture index."""

from __future__ import annotations

import json

import pytest
from PIL import Image

from medarot import textures


@pytest.fixture
def exported(project, pack):
    """A texture 'exported from the dump' sitting in the work area."""
    path = project.assets_dir / "dlg" / "Card_Change.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (8, 8), (10, 20, 30, 255))
    image.save(path)
    return path


def test_r8_import_stores_only_the_difference(project, pack, exported, tmp_path):
    """SPEC-003/R-8."""
    edited = Image.open(exported).convert("RGBA")
    edited.putpixel((3, 3), (255, 255, 255, 255))
    edited_path = tmp_path / "Card_Change.png"
    edited.save(edited_path)

    result = textures.import_edited(project, pack, edited_path)
    assert result.name == "Card_Change"
    assert result.delta.exists() and result.mask.exists()
    assert result.percent == pytest.approx(100.0 / 64)

    overlay = Image.open(result.delta).convert("RGBA")
    assert overlay.getpixel((3, 3)) == (255, 255, 255, 255)
    assert overlay.getpixel((0, 0)) == (0, 0, 0, 0)


def test_r8_import_resizes_a_mismatched_edit(project, pack, exported, tmp_path):
    edited = Image.new("RGBA", (16, 16), (255, 0, 0, 255))
    edited_path = tmp_path / "Card_Change.png"
    edited.save(edited_path)
    result = textures.import_edited(project, pack, edited_path)
    assert Image.open(result.delta).size == (8, 8)


def test_r8_import_refuses_an_unchanged_image(project, pack, exported):
    with pytest.raises(textures.TextureError, match="identical"):
        textures.import_edited(project, pack, exported)


def test_import_uses_the_name_flag_when_the_file_differs(project, pack, exported,
                                                        tmp_path):
    edited = Image.new("RGBA", (8, 8), (1, 2, 3, 255))
    path = tmp_path / "my-edit-v2.png"
    edited.save(path)
    result = textures.import_edited(project, pack, path, name="Card_Change")
    assert result.name == "Card_Change"


def test_import_of_a_missing_file_fails(project, pack, tmp_path):
    with pytest.raises(textures.TextureError, match="not found"):
        textures.import_edited(project, pack, tmp_path / "nope.png")


def test_unknown_texture_says_how_to_look_it_up(project, pack, tmp_path):
    edited = Image.new("RGBA", (4, 4), (0, 0, 0, 255))
    path = tmp_path / "Nonexistent.png"
    edited.save(path)
    with pytest.raises(textures.TextureError, match="assets --list"):
        textures.import_edited(project, pack, path)


def test_preview_rebuilds_the_final_texture(project, pack, exported, tmp_path):
    edited = Image.open(exported).convert("RGBA")
    edited.putpixel((1, 1), (9, 9, 9, 255))
    edited_path = tmp_path / "Card_Change.png"
    edited.save(edited_path)
    textures.import_edited(project, pack, edited_path)

    out = textures.preview(project, pack, "Card_Change")
    assert Image.open(out).getpixel((1, 1)) == (9, 9, 9, 255)


def test_preview_without_a_delta_fails(project, pack, exported):
    with pytest.raises(textures.TextureError, match="no delta"):
        textures.preview(project, pack, "Card_Change")


def test_r9_index_is_documentation_only(project, pack):
    """SPEC-003/R-9: textures.json describes, it does not drive the build."""
    textures.save_index(pack, [{"texture": "Card_Change", "text": "CHANGE"}])
    assert textures.load_index(pack)["Card_Change"]["text"] == "CHANGE"
    doc = json.loads(pack.texture_index_file.read_text(encoding="utf-8"))
    assert doc["textures"][0]["texture"] == "Card_Change"


def test_status_merges_deltas_and_notes(project, pack, exported, tmp_path):
    textures.save_index(pack, [{"texture": "Card_Change", "text": "CHANGE"},
                               {"texture": "Other", "text": "TODO"}])
    edited = Image.open(exported).convert("RGBA")
    edited.putpixel((0, 0), (7, 7, 7, 255))
    edited_path = tmp_path / "Card_Change.png"
    edited.save(edited_path)
    textures.import_edited(project, pack, edited_path)

    rows = {row["texture"]: row for row in textures.status(project, pack)}
    assert rows["Card_Change"]["delta"] is True
    assert rows["Other"]["delta"] is False
    assert rows["Card_Change"]["text"] == "CHANGE"


def test_no_index_means_no_notes(project, pack):
    assert textures.load_index(pack) == {}
    assert textures.status(project, pack) == []


def test_edge_contact_flags_only_new_overflow(project, pack, tmp_path):
    """SPEC-003/R-10: an edit that runs off the side the original did not use.

    This is the failure that bit the Spanish pack: translated lines are wider than
    the Japanese they replace and the game clips them without a word.
    """
    from PIL import Image
    from medarot import textures as mod

    # original: art with a 2px transparent margin on every side
    original = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    for x in range(2, 14):
        for y in range(2, 14):
            original.putpixel((x, y), (10, 10, 10, 255))

    inside = original.copy()
    inside.putpixel((8, 8), (255, 255, 255, 255))
    _, mask, _ = __import__("medarot.formats.texdiff", fromlist=["x"]).make_diff(
        original, inside)
    assert mod.edge_contact(original, inside, mask) == ()

    spilling = original.copy()
    for x in range(0, 16):
        spilling.putpixel((x, 8), (255, 255, 255, 255))
    _, mask2, _ = __import__("medarot.formats.texdiff", fromlist=["x"]).make_diff(
        original, spilling)
    assert set(mod.edge_contact(original, spilling, mask2)) == {"left", "right"}


def test_edge_contact_ignores_full_bleed_textures(project, pack):
    """A texture whose art already fills the frame must not be flagged."""
    from PIL import Image
    from medarot.formats import texdiff
    from medarot import textures as mod

    original = Image.new("RGBA", (8, 8), (10, 10, 10, 255))   # full bleed
    edited = original.copy()
    for x in range(8):
        edited.putpixel((x, 4), (255, 255, 255, 255))
    _, mask, _ = texdiff.make_diff(original, edited)
    assert mod.edge_contact(original, edited, mask) == ()


def test_import_reports_edge_contact(project, pack, exported, tmp_path):
    from PIL import Image

    original = Image.open(exported).convert("RGBA")
    original.putalpha(0)
    for x in range(2, 6):
        for y in range(2, 6):
            original.putpixel((x, y), (10, 10, 10, 255))
    original.save(exported)

    edited = Image.open(exported).convert("RGBA")
    for x in range(8):
        edited.putpixel((x, 4), (255, 255, 255, 255))
    path = tmp_path / "Card_Change.png"
    edited.save(path)

    result = textures.import_edited(project, pack, path)
    assert not result.fits()
    assert "left" in result.touches and "right" in result.touches
