"""End-to-end build against a real dump (SPEC-006).

These are the tests that exercise the Unity-facing steps — bundle labels, scene
labels, textures, sprite atlases, fonts. They cannot run without the game, so they
are marked ``game`` and skipped on a clean checkout.

They are slow on purpose: they patch the real files and read them back.
"""

from __future__ import annotations

import dataclasses

import pytest

from medarot import build, lang, unity
from medarot.formats import idxres

pytestmark = pytest.mark.game


@pytest.fixture
def spanish(real_project):
    return lang.get(real_project.langs, "es")


def test_tables_step_matches_the_shipped_translation(real_project, spanish, tmp_path):
    """Every translated string lands, and the file still parses."""
    project = dataclasses.replace(real_project, build=tmp_path / "build")
    report = build.run(project, spanish, only=["tables"])
    assert report.applied >= 3500, report.applied
    assert report.files >= 25

    tables_dir = report.mod_dir / "romfs/Data/StreamingAssets/IdxResData"
    for path in tables_dir.glob("*.bytes"):
        assert idxres.roundtrip_ok(path), path.name


def test_full_build_touches_every_layer(real_project, spanish, tmp_path):
    """The whole pipeline, on the real game: tables, bundles, scenes, textures."""
    project = dataclasses.replace(real_project, build=tmp_path / "build")
    report = build.run(project, spanish)

    by_step = {result.name: result for result in report.results}
    assert by_step["tables"].applied >= 3500
    assert by_step["fonts"].applied >= 1, "font fallbacks were not applied"
    assert by_step["bundle-labels"].applied >= 1
    assert by_step["scene-labels"].applied >= 1
    assert by_step["bundle-textures"].applied + by_step["scene-textures"].applied >= 1

    romfs = report.mod_dir / "romfs"
    assert list(romfs.glob("Data/StreamingAssets/aa/Switch/*.bundle"))
    assert list(romfs.glob("Data/level*")) or list(romfs.glob("Data/*.assets"))


def test_patched_bundles_still_open(real_project, spanish, tmp_path):
    """A bundle that UnityPy cannot reopen would be a black screen in game."""
    project = dataclasses.replace(real_project, build=tmp_path / "build")
    report = build.run(project, spanish, only=["fonts", "bundle-labels"])
    bundles = list((report.mod_dir / "romfs/Data/StreamingAssets/aa/Switch")
                   .glob("*.bundle"))
    assert bundles
    for path in bundles[:10]:
        env = unity.load(path)
        assert list(env.objects), f"{path.name} has no objects after patching"


def test_no_japanese_left_in_the_patched_tables(real_project, spanish, tmp_path):
    """Whatever the pack translates must be gone from the output."""
    from medarot import catalog

    project = dataclasses.replace(real_project, build=tmp_path / "build")
    report = build.run(project, spanish, only=["tables"])

    translated_keys = {
        (table, entry["row"], entry.get("n", 0), entry["sub"], entry["col"])
        for table in spanish.tables()
        for entry in spanish.table_catalog(table).entries if entry.get("t")
    }
    leftovers = []
    tables_dir = report.mod_dir / "romfs/Data/StreamingAssets/IdxResData"
    for path in sorted(tables_dir.glob("*.bytes")):
        name = idxres.table_name(path)
        table = idxres.parse_file(path)
        seen: dict[str, int] = {}
        for row in table.rows:
            occurrence = seen.get(row.key, 0)
            seen[row.key] = occurrence + 1
            for sub_index, sub in enumerate(row.cells):
                for col_index, col_name in table.string_columns():
                    key = (name, row.key, occurrence, sub_index, col_name)
                    if key in translated_keys and catalog.has_source_text(sub[col_index]):
                        leftovers.append(key)
    assert not leftovers, f"{len(leftovers)} cells still hold source text"


def test_rebuilt_textures_match_their_delta(real_project, spanish, tmp_path):
    """The texture that ends up in the mod is the one the delta describes.

    Not byte-for-byte: ASTC 5x5 is lossy, and re-encoding an untouched texture
    already moves ~1% of its pixels. The check is on decoded pixels, with the
    codec's own error as the tolerance.
    """
    import dataclasses

    from PIL import ImageChops

    from medarot import extract
    from medarot.formats import texdiff

    project = dataclasses.replace(real_project, build=tmp_path / "build")
    report = build.run(project, spanish, only=["bundle-textures", "scene-textures"])
    assert report.applied >= 1

    deltas = spanish.deltas()
    checked = 0
    for path in sorted((report.mod_dir / "romfs").rglob("*")):
        if not path.is_file():
            continue
        try:
            env = unity.load(path)
        except Exception:
            continue
        for _, data in unity.textures(env):
            delta = deltas.get(data.m_Name)
            if delta is None:
                continue
            expected = texdiff.load_translated(
                extract.find_texture(project, data.m_Name), delta)
            got = data.image.convert("RGBA")
            if expected.size != got.size:
                expected = expected.resize(got.size)
            peak = max(c.getextrema()[1]
                       for c in ImageChops.difference(expected, got).split())
            assert peak <= 80, f"{data.m_Name}: peaked at {peak}, that is not codec loss"
            checked += 1
    assert checked >= 10, f"only checked {checked} textures"
