"""SPEC-006 — build pipeline (the parts that need no Unity files)."""

from __future__ import annotations

import json

import pytest

from medarot import build, catalog
from medarot.formats import idxres

from .conftest import JP_HELLO


def build_tables(project, pack, **kwargs):
    return build.run(project, pack, only=["tables"], **kwargs)


def output_table(project, pack, name="Test"):
    path = (project.build_lang(pack.code) / pack.mod_name / "romfs"
            / f"Data/StreamingAssets/IdxResData/IdxRes_{name}.bytes")
    return idxres.parse_file(path) if path.exists() else None


def test_applies_translations_into_the_table(project_with_romfs, pack):
    report = build_tables(project_with_romfs, pack)
    assert report.applied == 2
    table = output_table(project_with_romfs, pack)
    assert table.rows[0].cells[0][3] == "Accept"
    assert table.rows[2].cells[0][3] == "Menu"


def test_untranslated_cells_are_left_alone(project_with_romfs, pack):
    build_tables(project_with_romfs, pack)
    table = output_table(project_with_romfs, pack)
    # the second sub-row of Dup has no translation in the fixture
    assert table.rows[3].cells[1][3] == "ASCII only"


def test_r2_build_is_reproducible(project_with_romfs, pack):
    first = build_tables(project_with_romfs, pack)
    data_one = (first.mod_dir / "romfs/Data/StreamingAssets/IdxResData"
                / "IdxRes_Test.bytes").read_bytes()
    second = build_tables(project_with_romfs, pack)
    data_two = (second.mod_dir / "romfs/Data/StreamingAssets/IdxResData"
                / "IdxRes_Test.bytes").read_bytes()
    assert data_one == data_two


def test_r2_a_fresh_build_wipes_the_previous_one(project_with_romfs, pack):
    report = build_tables(project_with_romfs, pack)
    stray = report.mod_dir / "romfs" / "stray.txt"
    stray.write_text("x", encoding="utf-8")
    build_tables(project_with_romfs, pack)
    assert not stray.exists()


def test_keep_preserves_the_previous_build(project_with_romfs, pack):
    report = build_tables(project_with_romfs, pack)
    stray = report.mod_dir / "romfs" / "stray.txt"
    stray.write_text("x", encoding="utf-8")
    build_tables(project_with_romfs, pack, keep=True)
    assert stray.exists()


def test_r3_unknown_step_is_an_error(project_with_romfs, pack):
    with pytest.raises(build.BuildError, match="unknown step"):
        build.run(project_with_romfs, pack, only=["nonsense"])


def test_r3_skip_and_only_select_steps(project_with_romfs, pack):
    report = build.run(project_with_romfs, pack, skip=build.STEPS[1:])
    assert [r.name for r in report.results] == ["tables"]


def test_r5_output_is_re_read_after_writing(project_with_romfs, pack):
    """SPEC-006/R-5: the written table parses back."""
    report = build_tables(project_with_romfs, pack)
    path = (report.mod_dir / "romfs/Data/StreamingAssets/IdxResData"
            / "IdxRes_Test.bytes")
    assert idxres.roundtrip_ok(path)


def test_r7_missing_row_is_reported_and_skipped(project_with_romfs, pack):
    cat = pack.table_catalog("Test")
    cat.entries.append({"row": "Ghost", "sub": 0, "col": "text",
                        "src": "aaaaaaaaaaaa", "t": "nowhere"})
    cat.save(pack.table_file("Test"))
    report = build_tables(project_with_romfs, pack)
    assert report.applied == 2
    assert any("Ghost" in note for r in report.results for note in r.notes)


def test_r7_missing_column_is_reported_and_skipped(project_with_romfs, pack):
    cat = pack.table_catalog("Test")
    cat.entries.append({"row": "Ok", "sub": 0, "col": "nope",
                        "src": "aaaaaaaaaaaa", "t": "x"})
    cat.save(pack.table_file("Test"))
    report = build_tables(project_with_romfs, pack)
    assert any("nope" in note for r in report.results for note in r.notes)


def test_stale_key_is_skipped_by_default(project_with_romfs, pack):
    """SPEC-005/R-5: a changed source string means the translation is not applied."""
    cat = pack.table_catalog("Test")
    cat.entries[0]["src"] = "000000000000"
    cat.save(pack.table_file("Test"))

    report = build_tables(project_with_romfs, pack)
    assert report.applied == 1
    assert any("stale" in note for r in report.results for note in r.notes)
    table = output_table(project_with_romfs, pack)
    assert table.rows[0].cells[0][3] == JP_HELLO       # left untouched


def test_allow_stale_applies_anyway(project_with_romfs, pack):
    cat = pack.table_catalog("Test")
    cat.entries[0]["src"] = "000000000000"
    cat.save(pack.table_file("Test"))
    report = build_tables(project_with_romfs, pack, allow_stale=True)
    assert report.applied == 2


def test_r10_ascii_mode_degrades_accents(project_with_romfs, pack):
    """SPEC-006/R-10."""
    data = json.loads((pack.directory / "lang.json").read_text(encoding="utf-8"))
    data["ascii_fallback"] = {"é": "e", "¡": ""}
    (pack.directory / "lang.json").write_text(json.dumps(data), encoding="utf-8")

    cat = pack.table_catalog("Test")
    cat.entries[0]["t"] = "¡Café!"
    cat.save(pack.table_file("Test"))

    from medarot.lang import LanguagePack
    reloaded = LanguagePack.load(pack.directory)
    build.run(project_with_romfs, reloaded, only=["tables"], ascii_mode=True)
    table = output_table(project_with_romfs, reloaded)
    assert table.rows[0].cells[0][3] == "Cafe!"


def test_ascii_mode_without_a_map_warns(project_with_romfs, pack):
    report = build.run(project_with_romfs, pack, only=["tables"], ascii_mode=True)
    assert any("ascii_fallback" in w for w in report.warnings)


def test_warns_when_the_cache_is_missing(project_with_romfs, pack):
    """SPEC-006/R-4: a build without 'prepare' still works, and says so."""
    report = build_tables(project_with_romfs, pack)
    assert any("prepared cache" in w for w in report.warnings)


def test_no_warning_when_the_cache_exists(project_with_romfs, pack):
    project_with_romfs.base_cache.mkdir(parents=True)
    report = build_tables(project_with_romfs, pack)
    assert not any("prepared cache" in w for w in report.warnings)


def test_mod_extras_are_copied_verbatim(project_with_romfs, pack):
    extras = pack.directory / "mod_extras" / "romfs" / "Data" / "extra.bin"
    extras.parent.mkdir(parents=True)
    extras.write_bytes(b"\x01\x02")
    report = build_tables(project_with_romfs, pack)
    assert (report.mod_dir / "romfs/Data/extra.bin").read_bytes() == b"\x01\x02"


def test_build_without_romfs_fails_clearly(project, pack):
    from medarot.config import ConfigError
    with pytest.raises(ConfigError, match="setup --romfs"):
        build_tables(project, pack)


def test_describe_mod_lists_contents(project_with_romfs, pack):
    report = build_tables(project_with_romfs, pack)
    assert any("data tables" in line for line in build.describe_mod(report.mod_dir))


def test_fingerprints_match_the_source(project_with_romfs, pack):
    """The fixture's own keys are what a real extract would produce."""
    entry = pack.table_catalog("Test").entries[0]
    assert entry["src"] == catalog.fingerprint(JP_HELLO)


def test_r4_cached_files_are_carried_into_the_mod(project_with_romfs, pack):
    """SPEC-006/R-4: a bundle that only needed the metric fix must still ship.

    Found by diffing a real build against the reference pipeline: 28 bundles that
    no other step touches were missing, so those screens kept the cramped text.
    """
    cached = project_with_romfs.base_cache / "Data/StreamingAssets/aa/Switch/only.bundle"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"metrics-fixed")

    report = build_tables(project_with_romfs, pack)
    shipped = report.mod_dir / "romfs/Data/StreamingAssets/aa/Switch/only.bundle"
    assert shipped.read_bytes() == b"metrics-fixed"


def test_r4_a_step_output_wins_over_the_cache(project_with_romfs, pack):
    """The cache never overwrites what a step wrote: steps read from it already."""
    table = "Data/StreamingAssets/IdxResData/IdxRes_Test.bytes"
    cached = project_with_romfs.base_cache / table
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"stale cache copy")

    report = build_tables(project_with_romfs, pack)
    assert (report.mod_dir / "romfs" / table).read_bytes() != b"stale cache copy"


def test_cache_is_not_carried_when_the_pack_opts_out(project_with_romfs, pack):
    import json
    from medarot.lang import LanguagePack

    data = json.loads((pack.directory / "lang.json").read_text(encoding="utf-8"))
    data["font"] = {"fix_tmp_metrics": False}
    (pack.directory / "lang.json").write_text(json.dumps(data), encoding="utf-8")

    cached = project_with_romfs.base_cache / "Data/StreamingAssets/aa/Switch/only.bundle"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"metrics-fixed")

    report = build.run(project_with_romfs, LanguagePack.load(pack.directory),
                       only=["tables"])
    assert not (report.mod_dir
                / "romfs/Data/StreamingAssets/aa/Switch/only.bundle").exists()


def test_a_cache_from_another_dump_is_reported(project_with_romfs, pack):
    """Base game and update share a title id; only a fingerprint tells them apart."""
    project_with_romfs.base_cache.mkdir(parents=True)
    project_with_romfs.record_dump()
    assert not project_with_romfs.dump_changed()

    # the same title, a different dump: one more table on disk
    (project_with_romfs.tables_dir / "IdxRes_Extra.bytes").write_bytes(b"x")
    assert project_with_romfs.dump_changed()

    report = build_tables(project_with_romfs, pack)
    assert any("different dump" in w for w in report.warnings)


def test_no_warning_when_the_dump_is_the_same(project_with_romfs, pack):
    project_with_romfs.base_cache.mkdir(parents=True)
    project_with_romfs.record_dump()
    report = build_tables(project_with_romfs, pack)
    assert not any("different dump" in w for w in report.warnings)
