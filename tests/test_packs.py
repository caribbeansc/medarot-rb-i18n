"""The language packs shipped in this repository must be publishable.

These tests run against ``langs/`` itself, so a pull request that pastes source
text into a translation fails CI (SPEC-005/R-4, SPEC-004).
"""

from __future__ import annotations

import json

import pytest

from medarot import catalog, lang

from .conftest import REPO

LANGS = REPO / "langs"
PACKS = lang.discover(LANGS)
CODES = [pack.code for pack in PACKS]


def test_repository_ships_at_least_one_language():
    assert CODES, "langs/ is empty"


@pytest.mark.parametrize("code", CODES)
def test_pack_loads(code):
    """SPEC-004/R-2, R-3: every shipped pack is valid."""
    pack = lang.get(LANGS, code)
    assert pack.name and pack.mod_name


@pytest.mark.parametrize("code", CODES)
def test_pack_has_no_source_text(code):
    """SPEC-005/R-4: this is the guarantee that lets the repo be public."""
    pack = lang.get(LANGS, code)
    offenders = catalog.scan_tree_for_source_text(pack.directory)
    assert not offenders, f"{code}: source text in {offenders}"


@pytest.mark.parametrize("code", CODES)
def test_catalogs_are_well_formed(code):
    pack = lang.get(LANGS, code)
    for table in pack.tables():
        cat = pack.table_catalog(table)
        for entry in cat.entries:
            assert set(entry) >= {"row", "sub", "col", "src", "t"}, entry
            assert isinstance(entry["sub"], int)
            assert len(entry["src"]) == catalog.FINGERPRINT_LEN
            assert "|" not in entry["row"] and "|" not in entry["col"], (
                "the CSV key separator must not appear in a key")
    for entry in pack.label_catalog().entries:
        assert len(entry["src"]) == catalog.FINGERPRINT_LEN


@pytest.mark.parametrize("code", CODES)
def test_no_duplicate_keys(code):
    """SPEC-005/R-9: one entry per (position, fingerprint).

    A position may legitimately appear twice: the same cell holds different text
    in the base game and after the update: but never twice for the same text.
    """
    pack = lang.get(LANGS, code)
    for table in pack.tables():
        cat = pack.table_catalog(table)
        keys = [catalog.entry_key(e, catalog.KIND_IDXRES) for e in cat.entries]
        assert len(keys) == len(set(keys)), f"{code}/{table} has duplicate keys"
    labels = [e["src"] for e in pack.label_catalog().entries]
    assert len(labels) == len(set(labels)), f"{code}/labels has duplicate keys"


@pytest.mark.parametrize("code", CODES)
def test_every_delta_has_a_mask(code):
    """SPEC-003/R-5: an overlay without its mask cannot be applied correctly."""
    pack = lang.get(LANGS, code)
    from medarot.formats import texdiff

    for name, delta in pack.deltas().items():
        assert texdiff.mask_path(delta).exists(), f"{code}/{name}: mask missing"


@pytest.mark.parametrize("code", CODES)
def test_texture_index_matches_the_deltas(code):
    """Every delta should be documented, and every note should name a real file."""
    pack = lang.get(LANGS, code)
    notes = {item["texture"] for item in pack.texture_notes()}
    deltas = set(pack.deltas())
    undocumented = deltas - notes
    assert not undocumented, f"{code}: deltas with no entry in textures.json: {undocumented}"


def test_packs_agree_on_the_key_set():
    """A new language starts from the same keys, so packs stay comparable."""
    if len(PACKS) < 2:
        pytest.skip("only one language in this checkout")
    reference, *others = PACKS
    expected = {table: {catalog.entry_key(e, catalog.KIND_IDXRES)
                        for e in reference.table_catalog(table).entries}
                for table in reference.tables()}
    for pack in others:
        for table, keys in expected.items():
            mine = {catalog.entry_key(e, catalog.KIND_IDXRES)
                    for e in pack.table_catalog(table).entries}
            missing = keys - mine
            assert not missing, f"{pack.code}/{table} is missing {len(missing)} keys"


@pytest.mark.parametrize("code", CODES)
def test_lang_json_is_pretty_printed(code):
    """Hand-edited files: keep them readable so diffs stay reviewable."""
    raw = (LANGS / code / "lang.json").read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert json.loads(raw)["code"] == code
    assert "\n  " in raw, "lang.json should be indented"
