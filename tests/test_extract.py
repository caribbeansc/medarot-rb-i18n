"""Reading the user's dump: tables, inventories, texture index.

The synthetic tests use a one-table fake romfs; the ``game`` ones need a real dump
and are the reason we can claim the pipeline reproduces the shipped translation.
"""

from __future__ import annotations

import pytest

from medarot import catalog, extract
from medarot.formats import idxres

from .conftest import JP_HELLO, JP_LONG, JP_MENU


def test_reads_only_japanese_string_cells(project_with_romfs):
    found = extract.read_tables(project_with_romfs)
    cells = found["Test"]
    texts = {cell.text for cell in cells}
    assert texts == {JP_HELLO, JP_MENU, JP_LONG}
    assert all(cell.col == "text" for cell in cells)


def test_addresses_include_the_sub_row(project_with_romfs):
    found = extract.read_tables(project_with_romfs)
    keys = {(c.row, c.sub, c.col) for c in found["Test"]}
    assert ("Dup", 0, "text") in keys


def test_raw_dump_is_written(project_with_romfs):
    extract.read_tables(project_with_romfs)
    dump = project_with_romfs.raw_dir / "Test.json"
    assert dump.exists()
    assert "columns" in dump.read_text(encoding="utf-8")


def test_a_corrupt_table_is_skipped_not_fatal(project_with_romfs, capsys):
    """SPEC-001/R-3 in practice: a table that fails round-trip is not trusted."""
    path = project_with_romfs.tables_dir / "IdxRes_Broken.bytes"
    path.write_bytes(b"\x0c\x00\x00\x00" + b"IdxRes2[2.0]" + b"\x00" * 4)
    with pytest.raises(Exception):
        # a header this broken cannot even be parsed
        extract.read_tables(project_with_romfs)


def test_missing_tables_directory_is_reported(project):
    project.romfs = project.root / "nope"
    with pytest.raises(Exception):
        extract.read_tables(project)


def test_inventory_round_trip(project_with_romfs):
    extract.write_inventory(project_with_romfs, "tables", {"Test": []})
    assert extract.read_inventory(project_with_romfs, "tables") == {"Test": []}
    assert extract.read_inventory(project_with_romfs, "nothing") is None


def test_refresh_all_can_skip_the_slow_scans(project_with_romfs):
    summary = extract.refresh_all(project_with_romfs, tables=True, bundles=False,
                                  scenes=False)
    assert summary == {"tables": 3}


def test_walk_strings_finds_nested_values():
    tree = {"m_Name": "x", "child": {"m_text": "hola"}, "list": [{"m_text": "b"}]}
    found = dict(extract._walk_strings(tree))
    assert found[".child.m_text"] == "hola"
    assert found[".list[0].m_text"] == "b"


# --------------------------------------------------------------- real dump --

@pytest.mark.game
def test_every_table_parses_and_the_counts_are_stable(real_project):
    files = sorted(real_project.tables_dir.glob("IdxRes_*.bytes"))
    assert len(files) == 107, f"expected 107 tables, found {len(files)}"
    found = extract.read_tables(real_project, dump_raw=False)
    total = sum(len(cells) for cells in found.values())
    assert len(found) == 29, "29 tables hold Japanese text"
    assert total == 3722, f"expected 3722 translatable cells, got {total}"


@pytest.mark.game
def test_fingerprints_are_unique_across_the_whole_game(real_project):
    """SPEC-005/R-3 for real: 48 bits is enough for this game's text."""
    found = extract.read_tables(real_project, dump_raw=False)
    by_fingerprint = {}
    collisions = []
    for cells in found.values():
        for cell in cells:
            digest = catalog.fingerprint(cell.text)
            previous = by_fingerprint.setdefault(digest, cell.text)
            if previous != cell.text:
                collisions.append(digest)
    assert not collisions


@pytest.mark.game
def test_the_spanish_pack_covers_this_dump(real_project):
    """Every translatable cell has an entry written for *this* dump's wording.

    A position may carry several entries — one per version of the game
    (SPEC-005/R-9) — so what matters is that one of them matches, not that all do.
    """
    from medarot import lang

    pack = lang.get(real_project.langs, "es")
    found = extract.read_tables(real_project, dump_raw=False)

    index = {}
    for table in pack.tables():
        for entry in pack.table_catalog(table).entries:
            key = (table, entry["row"], entry.get("n", 0), entry["sub"], entry["col"])
            index.setdefault(key, set()).add(entry.get("src", ""))

    policy = {"StaffCredits", "SupecialSupporter"}
    uncovered = []
    for table, cells in found.items():
        if table in policy:
            continue
        for cell in cells:
            key = (table, cell.row, cell.n, cell.sub, cell.col)
            if catalog.fingerprint(cell.text) not in index.get(key, ()):
                uncovered.append(key)
    assert not uncovered, f"{len(uncovered)} cells have no entry for this dump"


@pytest.mark.game
def test_round_trip_of_the_whole_table_set(real_project):
    bad = [p.name for p in sorted(real_project.tables_dir.glob("IdxRes_*.bytes"))
           if not idxres.roundtrip_ok(p)]
    assert not bad
