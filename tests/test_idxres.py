"""SPEC-001 — IdxRes2[2.0] table format."""

from __future__ import annotations

import struct

import pytest

from medarot.formats import idxres

from .conftest import JP_HELLO


def test_r1_rejects_wrong_magic():
    """SPEC-001/R-1: a buffer without the exact magic is refused."""
    payload = b"\x04\x00\x00\x00" + b"nope"
    with pytest.raises(ValueError, match="magic"):
        idxres.parse(payload)


def test_r1_rejects_garbage():
    """SPEC-001/R-1: random bytes are refused, not half-parsed."""
    with pytest.raises(ValueError):
        idxres.parse(b"\xff\xff\xff\xff\x00")


def test_r2_rejects_trailing_bytes(sample_table):
    """SPEC-001/R-2: trailing bytes are an error and are counted."""
    data = idxres.build(sample_table) + b"junk"
    with pytest.raises(ValueError, match="4 bytes left unparsed"):
        idxres.parse(data)


def test_r2_rejects_truncated(sample_table):
    """SPEC-001/R-2: a truncated buffer is refused."""
    data = idxres.build(sample_table)
    with pytest.raises((ValueError, struct.error)):
        idxres.parse(data[:-6])


def test_r3_roundtrip_is_byte_exact(sample_table):
    """SPEC-001/R-3: build(parse(x)) == x."""
    data = idxres.build(sample_table)
    assert idxres.build(idxres.parse(data)) == data


def test_r3_roundtrip_preserves_every_value(sample_table):
    """SPEC-001/R-3: values survive, not just the byte length."""
    parsed = idxres.parse(idxres.build(sample_table))
    assert parsed.sheet == sample_table.sheet
    assert parsed.start_cell == sample_table.start_cell
    assert [c.name for c in parsed.columns] == [c.name for c in sample_table.columns]
    assert parsed.rows[0].cells[0][3] == JP_HELLO
    assert parsed.rows[0].cells[0][4] == [1, 2, 3]
    assert parsed.rows[0].cells[0][6] == {"hex": "ff0000ff"}
    assert parsed.rows[1].cells[0][2] is False


def test_r4_unknown_column_type_is_rejected(sample_table):
    """SPEC-001/R-4: an unknown column type raises on read and on write."""
    sample_table.columns[0].type = 6
    with pytest.raises(ValueError, match="unknown column type"):
        idxres.build(sample_table)

    # and on the way in: hand-craft a header with type 6
    out = bytearray()
    for text in (idxres.MAGIC, "a", "b", "c", "B3"):
        raw = text.encode()
        out += struct.pack("<I", len(raw)) + raw
    out += struct.pack("<I", 1) + struct.pack("<I", 6)
    raw = b"col"
    out += struct.pack("<I", len(raw)) + raw
    out += struct.pack("<I", 0)
    with pytest.raises(ValueError, match="unknown column type 6"):
        idxres.parse(bytes(out))


def test_r5_only_string_columns_are_translatable(sample_table):
    """SPEC-001/R-5: only type 3 columns count as text."""
    assert sample_table.string_columns() == [(3, "text")]


def test_r6_duplicate_keys_and_order_are_kept(sample_table):
    """SPEC-001/R-6: repeated row keys are all kept, in order."""
    parsed = idxres.parse(idxres.build(sample_table))
    assert [row.key for row in parsed.rows] == ["Ok", "Empty", "Dup", "Dup"]
    assert len(parsed.rows[3].cells) == 2


def test_r7_cell_count_mismatch_names_the_row(sample_table):
    """SPEC-001/R-7: a short sub-row is refused, with its key in the message."""
    sample_table.rows[0].cells[0].pop()
    with pytest.raises(ValueError, match="row 'Ok'"):
        idxres.build(sample_table)


def test_r8_length_prefix_counts_bytes_not_characters(sample_table):
    """SPEC-001/R-8: a 3-byte kanji counts as 3."""
    sample_table.rows[0].cells[0][3] = "あ"      # 3 bytes in UTF-8
    data = idxres.build(sample_table)
    assert struct.pack("<I", 3) + "あ".encode("utf-8") in data


def test_r9_empty_string_survives(sample_table):
    """SPEC-001/R-9: an empty string cell is preserved."""
    parsed = idxres.parse(idxres.build(sample_table))
    assert parsed.rows[1].cells[0][3] == ""


def test_column_index_and_name_helpers(sample_table):
    assert sample_table.column_index("text") == 3
    with pytest.raises(KeyError):
        sample_table.column_index("nope")
    assert idxres.table_name("/x/IdxRes_Text_Menu.bytes") == "Text_Menu"


def test_parse_file_and_roundtrip_ok(tmp_path, sample_table):
    path = tmp_path / "IdxRes_Test.bytes"
    path.write_bytes(idxres.build(sample_table))
    assert idxres.parse_file(path).sheet == "Test"
    assert idxres.roundtrip_ok(path)


@pytest.mark.game
def test_r3_roundtrip_on_every_retail_table(real_project):
    """SPEC-001/R-3 against the real thing: all 107 tables, byte-exact."""
    files = sorted(real_project.tables_dir.glob("IdxRes_*.bytes"))
    assert len(files) >= 100, "not enough tables — is this the right romfs?"
    bad = [p.name for p in files if not idxres.roundtrip_ok(p)]
    assert not bad, f"round-trip failed for: {bad}"
