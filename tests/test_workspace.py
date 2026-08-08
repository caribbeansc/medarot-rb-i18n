"""SPEC-005 — the bilingual working copy and publishing (extract / sync)."""

from __future__ import annotations

import json

import pytest

from medarot import catalog, extract, workspace

from .conftest import JP_HELLO, JP_LONG, JP_MENU


@pytest.fixture
def space(project_with_romfs, pack):
    extract.refresh_all(project_with_romfs, tables=True, bundles=False, scenes=False)
    return workspace.Workspace(project=project_with_romfs, pack=pack)


def test_refresh_needs_an_inventory(project_with_romfs, pack):
    space = workspace.Workspace(project=project_with_romfs, pack=pack)
    with pytest.raises(workspace.WorkspaceError, match="mrb extract"):
        space.refresh()


def test_refresh_builds_a_bilingual_copy(space):
    """The work file has the source text; that is the point of it."""
    counts = space.refresh()
    assert counts["tables"] == 1
    entries = space.table_catalog("Test").entries
    sources = {e["jp"] for e in entries}
    assert JP_HELLO in sources and JP_MENU in sources
    assert all(e["src"] == catalog.fingerprint(e["jp"]) for e in entries)


def test_refresh_pulls_translations_from_the_pack(space):
    space.refresh()
    by_key = {catalog.entry_key(e, catalog.KIND_IDXRES): e
              for e in space.table_catalog("Test").entries}
    assert by_key[catalog.cell_key("Ok", 0, "text") + (catalog.fingerprint(JP_HELLO),)]["t"] == "Accept"
    assert by_key[catalog.cell_key("Dup", 0, "text") + (catalog.fingerprint(JP_MENU),)]["t"] == "Menu"


def test_refresh_is_idempotent_and_keeps_edits(space):
    space.refresh()
    assert space.set_translation("Test",
                          catalog.cell_key("Dup", 0, "text", 1)
                          + (catalog.fingerprint(JP_LONG),), "hand written")
    space.refresh()
    by_key = {catalog.entry_key(e, catalog.KIND_IDXRES): e
              for e in space.table_catalog("Test").entries}
    assert by_key[catalog.cell_key("Dup", 0, "text", 1) + (catalog.fingerprint(JP_LONG),)]["t"] == "hand written"


def test_r7_sync_publishes_without_source_text(space):
    """SPEC-005/R-7: sync strips jp, seen and where."""
    space.refresh()
    space.set_translation("Test", catalog.cell_key("Dup", 0, "text", 1)
                          + (catalog.fingerprint(JP_LONG),), "Third")
    counts = space.sync()

    published = space.pack.table_file("Test").read_text(encoding="utf-8")
    assert not catalog.has_source_text(published)
    assert "jp" not in json.loads(published)["entries"][0]
    assert counts["translations"] >= 3


def test_sync_keeps_translations_this_dump_does_not_know(space):
    """A different dump must not delete other people's work."""
    space.refresh()
    cat = space.pack.table_catalog("Test")
    cat.entries.append({"row": "OnlyInOtherVersion", "sub": 0, "col": "text",
                        "src": "ffffffffffff", "t": "kept"})
    cat.save(space.pack.table_file("Test"))

    counts = space.sync()
    assert counts["orphans"] == 1
    rows = {e["row"] for e in space.pack.table_catalog("Test").entries}
    assert "OnlyInOtherVersion" in rows


def test_sync_refuses_to_publish_source_text(space):
    space.refresh()
    space.set_translation("Test", catalog.cell_key("Ok", 0, "text")
                      + (catalog.fingerprint(JP_HELLO),), f"still {JP_HELLO}")
    with pytest.raises(workspace.WorkspaceError, match="refusing to publish"):
        space.sync()


def test_sync_without_a_working_copy_fails(project_with_romfs, pack):
    space = workspace.Workspace(project=project_with_romfs, pack=pack)
    with pytest.raises(workspace.WorkspaceError, match="nothing to sync"):
        space.sync()


def test_pending_lists_untranslated_only(space):
    space.refresh()
    pending = space.pending()
    keys = {catalog.entry_key(e, catalog.KIND_IDXRES) for _, e in pending}
    assert (catalog.cell_key("Ok", 0, "text") + (catalog.fingerprint(JP_HELLO),)
            not in keys)                                # already translated
    assert (catalog.cell_key("Dup", 0, "text", 1) + (catalog.fingerprint(JP_LONG),)
            in keys)


def test_source_map_maps_fingerprints_to_text(space):
    space.refresh()
    mapping = space.source_map()
    assert mapping[catalog.fingerprint(JP_HELLO)] == JP_HELLO


def test_stats(space):
    space.refresh()
    stats = space.stats()
    assert stats["text_total"] == 3
    assert stats["text_translated"] == 2


def test_set_translation_on_unknown_key_returns_false(space):
    space.refresh()
    assert space.set_translation("Test", catalog.cell_key("nope", 0, "text")
                                 + ("zzz",), "x") is False
