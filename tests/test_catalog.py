"""SPEC-005: copyright-safe translation keys."""

from __future__ import annotations

import json

import pytest

from medarot import catalog

from .conftest import JP_HELLO, JP_MENU


def test_r1_fingerprint_is_stable_and_short():
    """SPEC-005/R-1: 12 hex chars of SHA-256 over the UTF-8 bytes."""
    assert catalog.fingerprint("Ok") == "843ac01149cc"   # sha256("Ok")[:12]
    assert len(catalog.fingerprint(JP_HELLO)) == catalog.FINGERPRINT_LEN
    assert catalog.fingerprint(JP_HELLO) == catalog.fingerprint(JP_HELLO)
    assert catalog.fingerprint(JP_HELLO) != catalog.fingerprint(JP_MENU)


def test_r2_fingerprint_is_fixed_length_not_a_copy():
    """SPEC-005/R-2: length does not grow with the input."""
    short = catalog.fingerprint("a")
    long_one = catalog.fingerprint(JP_HELLO * 500)
    assert len(short) == len(long_one) == catalog.FINGERPRINT_LEN


def test_r3_collision_between_different_sources_is_reported():
    """SPEC-005/R-3: two different sources under one fingerprint is an error."""
    cat = catalog.Catalog(kind=catalog.KIND_LABELS)
    cat.entries = [
        {"src": "aaaaaaaaaaaa", "jp": JP_HELLO, "t": "one"},
        {"src": "aaaaaaaaaaaa", "jp": JP_MENU, "t": "two"},
    ]
    problems = cat.check_collisions()
    assert problems and "aaaaaaaaaaaa" in problems[0]


def test_r3_same_source_twice_is_not_a_collision():
    cat = catalog.Catalog(kind=catalog.KIND_LABELS)
    cat.entries = [{"src": "x", "jp": JP_HELLO, "t": "a"},
                   {"src": "x", "jp": JP_HELLO, "t": "a"}]
    assert cat.check_collisions() == []


@pytest.mark.parametrize("text,expected", [
    (JP_HELLO, True),          # hiragana
    (JP_MENU, True),           # katakana
    ("日本", True),             # kanji
    ("？", True),               # fullwidth punctuation: still the game's text
    ("　", True),               # ideographic space
    ("Aceptar", False),
    ("¡Vamos!", False),
    ("New Record", False),
    ("↑ ♪ -", False),
])
def test_r4_source_text_detection(text, expected):
    """SPEC-005/R-4: what counts as source text."""
    assert catalog.has_source_text(text) is expected


def test_r4_scan_tree_finds_and_skips_the_right_files(tmp_path):
    """SPEC-005/R-4: text files are scanned, binaries are skipped."""
    (tmp_path / "clean.json").write_text('{"t": "Aceptar"}', encoding="utf-8")
    (tmp_path / "dirty.json").write_text(f'{{"t": "{JP_HELLO}"}}', encoding="utf-8")
    (tmp_path / "art.png").write_bytes(JP_HELLO.encode("utf-8"))
    offenders = catalog.scan_tree_for_source_text(tmp_path)
    assert [p.split("/")[-1] for p in offenders] == ["dirty.json"]


def test_check_no_source_text_covers_notes():
    cat = catalog.Catalog(kind=catalog.KIND_LABELS)
    cat.entries = [{"src": "a", "t": "fine", "note": JP_MENU}]
    assert cat.check_no_source_text()


def test_entry_keys_by_kind():
    """SPEC-001/R-6 and SPEC-005/R-9: address plus fingerprint."""
    idx = {"row": "Ok", "sub": 0, "col": "text", "src": "a", "t": ""}
    assert catalog.entry_key(idx, catalog.KIND_IDXRES) == ("Ok", 0, 0, "text", "a")
    assert catalog.entry_key({**idx, "n": 1}, catalog.KIND_IDXRES) == \
        ("Ok", 1, 0, "text", "a")
    assert catalog.cell_position(idx) == ("Ok", 0, 0, "text")
    assert catalog.entry_key({"src": "z"}, catalog.KIND_LABELS) == "z"


def test_same_cell_with_different_source_text_is_two_entries():
    """SPEC-005/R-9: the update rewrote some cells; both spellings live on."""
    base = catalog.idxres_entry("Data05", 0, "text", "long original text")
    patched = catalog.idxres_entry("Data05", 0, "text", "?")
    assert catalog.cell_position(base) == catalog.cell_position(patched)
    assert (catalog.entry_key(base, catalog.KIND_IDXRES)
            != catalog.entry_key(patched, catalog.KIND_IDXRES))


def test_duplicate_row_keys_do_not_collide():
    """SPEC-001/R-6: two rows sharing a key are two different cells."""
    first = catalog.idxres_entry("Dup", 0, "text", "one")
    second = catalog.idxres_entry("Dup", 0, "text", "two", n=1)
    assert "n" not in first and second["n"] == 1
    assert (catalog.entry_key(first, catalog.KIND_IDXRES)
            != catalog.entry_key(second, catalog.KIND_IDXRES))


def test_r7_save_strips_source_text(tmp_path):
    """SPEC-005/R-7: publishing drops jp/seen/where."""
    cat = catalog.Catalog(kind=catalog.KIND_LABELS)
    cat.entries = [catalog.label_entry(JP_HELLO, "Hola", "a note")]
    cat.entries[0]["seen"] = 3
    cat.entries[0]["where"] = ["bundle"]
    path = tmp_path / "labels.json"
    cat.save(path, strip_source=True)

    doc = json.loads(path.read_text(encoding="utf-8"))
    entry = doc["entries"][0]
    assert entry == {"src": catalog.fingerprint(JP_HELLO), "t": "Hola",
                     "note": "a note"}
    assert not catalog.has_source_text(path.read_text(encoding="utf-8"))


def test_work_copy_keeps_source_text(tmp_path):
    cat = catalog.Catalog(kind=catalog.KIND_LABELS)
    cat.entries = [catalog.label_entry(JP_HELLO, "Hola")]
    path = tmp_path / "work.json"
    cat.save(path)
    assert JP_HELLO in path.read_text(encoding="utf-8")


def test_merge_never_overwrites_existing_work():
    """SPEC-005/R-7: re-extracting cannot clobber a translation in progress."""
    fresh = catalog.Catalog(kind=catalog.KIND_IDXRES)
    fresh.entries = [catalog.idxres_entry("Ok", 0, "text", JP_HELLO, "in progress"),
                     catalog.idxres_entry("No", 0, "text", JP_MENU, "")]
    published = catalog.Catalog(kind=catalog.KIND_IDXRES)
    published.entries = [
        {"row": "Ok", "sub": 0, "col": "text",
         "src": catalog.fingerprint(JP_HELLO), "t": "published"},
        {"row": "No", "sub": 0, "col": "text",
         "src": catalog.fingerprint(JP_MENU), "t": "filled in"},
    ]
    filled = fresh.merge_from(published)
    assert filled == 1
    assert fresh.entries[0]["t"] == "in progress"
    assert fresh.entries[1]["t"] == "filled in"


def test_load_rejects_malformed_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(catalog.CatalogError, match="invalid JSON"):
        catalog.Catalog.load(path, catalog.KIND_LABELS)


def test_load_rejects_wrong_shape(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('[1, 2, 3]', encoding="utf-8")
    with pytest.raises(catalog.CatalogError, match="entries"):
        catalog.Catalog.load(path, catalog.KIND_LABELS)


def test_load_missing_file_is_an_empty_catalog(tmp_path):
    cat = catalog.Catalog.load(tmp_path / "nope.json", catalog.KIND_LABELS)
    assert cat.entries == [] and cat.stats() == (0, 0)


def test_stats_and_untranslated():
    cat = catalog.Catalog(kind=catalog.KIND_LABELS)
    cat.entries = [{"src": "a", "t": "x"}, {"src": "b", "t": ""}]
    assert cat.stats() == (1, 2)
    assert [e["src"] for e in cat.untranslated()] == ["b"]
    assert cat.translations() == {"a": "x"}
    assert set(cat.by_fingerprint()) == {"a", "b"}


def test_field_order_is_stable(tmp_path):
    """Diffs stay reviewable: fields are written in a fixed order."""
    cat = catalog.Catalog(kind=catalog.KIND_IDXRES)
    cat.entries = [{"t": "x", "col": "text", "row": "Ok", "sub": 0, "src": "s"}]
    path = tmp_path / "t.json"
    cat.save(path)
    keys = list(json.loads(path.read_text(encoding="utf-8"))["entries"][0])
    assert keys == ["row", "sub", "col", "src", "t"]
