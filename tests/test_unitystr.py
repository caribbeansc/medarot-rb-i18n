"""SPEC-002. Unity serialized strings (raw patching)."""

from __future__ import annotations

import struct

import pytest

from medarot.formats import unitystr

from .conftest import JP_HELLO, JP_MENU


def blob(*texts: str, prefix: bytes = b"", suffix: bytes = b"") -> bytes:
    return prefix + b"".join(unitystr.encode_string(t) for t in texts) + suffix


def test_r1_finds_offset_and_text():
    """SPEC-002/R-1: returns the offset of the length prefix and the text."""
    raw = blob(JP_HELLO)
    assert unitystr.find_jp_strings(raw) == [(0, JP_HELLO)]


def test_r1_results_are_sorted():
    """SPEC-002/R-1: hits come back in offset order."""
    raw = blob(JP_HELLO, "ascii", JP_MENU)
    offsets = [offset for offset, _ in unitystr.find_jp_strings(raw)]
    assert offsets == sorted(offsets)
    assert len(offsets) == 2


def test_r2_padding_must_be_zero():
    """SPEC-002/R-2: non-zero padding means it is not a string."""
    encoded = bytearray(unitystr.encode_string(JP_HELLO))
    encoded[-1] = 0x41  # dirty the padding
    assert unitystr.find_jp_strings(bytes(encoded)) == []


def test_r2_rejects_invalid_utf8():
    """SPEC-002/R-2: a broken sequence is not accepted as a string."""
    raw = struct.pack("<i", 4) + b"\xe3\x81\xff\x41"
    assert unitystr.find_jp_strings(raw) == []


def test_r2_rejects_control_characters():
    """SPEC-002/R-2: control characters other than \\n \\r \\t disqualify a hit."""
    text = JP_HELLO + "\x01"
    raw = unitystr.encode_string(text)
    assert unitystr.find_jp_strings(raw) == []


def test_r2_accepts_newlines():
    """SPEC-002/R-2: \\n is allowed inside a string."""
    text = JP_HELLO + "\n" + JP_MENU
    assert unitystr.find_jp_strings(unitystr.encode_string(text)) == [(0, text)]


def test_r3_finds_strings_at_any_alignment():
    """SPEC-002/R-3: the scan does not depend on object alignment."""
    for pad in range(1, 8):
        raw = blob(JP_HELLO, prefix=b"\x7f" * pad)
        assert unitystr.find_jp_strings(raw) == [(pad, JP_HELLO)]


def test_r4_matches_do_not_overlap():
    """SPEC-002/R-4: no hit starts inside another hit."""
    text = JP_HELLO * 20
    raw = unitystr.encode_string(text)
    assert unitystr.find_jp_strings(raw) == [(0, text)]


def test_r5_verifies_length_before_writing():
    """SPEC-002/R-5: a wrong expected text or length raises."""
    raw = unitystr.encode_string(JP_HELLO)
    with pytest.raises(ValueError, match="unexpected length"):
        unitystr.replace_strings(raw, [(0, JP_HELLO + "extra", "x")])
    same_length = "あいうえお"                      # 15 bytes, like JP_HELLO
    assert len(same_length.encode()) == len(JP_HELLO.encode())
    with pytest.raises(ValueError, match="unexpected text"):
        unitystr.replace_strings(raw, [(0, same_length, "x")])


def test_r6_rewrites_length_and_padding():
    """SPEC-002/R-6: the new length is in bytes and padding is restored."""
    raw = blob(JP_HELLO, suffix=b"TAIL")
    out = unitystr.replace_strings(raw, [(0, JP_HELLO, "Hi")])
    assert struct.unpack_from("<i", out, 0)[0] == 2
    assert out.endswith(b"TAIL")
    assert len(out) % 4 == 0
    assert unitystr.find_jp_strings(out) == []


def test_r6_longer_replacement_shifts_the_tail():
    raw = blob(JP_HELLO, suffix=b"TAIL")
    out = unitystr.replace_strings(raw, [(0, JP_HELLO, "a much longer replacement")])
    assert out.endswith(b"TAIL")
    assert len(out) > len(raw)


def test_r7_replacing_with_itself_is_a_no_op():
    """SPEC-002/R-7."""
    raw = blob(JP_HELLO, "ascii", JP_MENU)
    assert unitystr.replace_strings(raw, [(0, JP_HELLO, JP_HELLO)]) == raw


def test_r8_ascii_only_strings_are_ignored():
    """SPEC-002/R-8: English text the game already ships is left alone."""
    assert unitystr.find_jp_strings(blob("New Record", "MAX")) == []


def test_multiple_replacements_in_one_pass():
    raw = blob(JP_HELLO, JP_MENU)
    hits = unitystr.find_jp_strings(raw)
    out = unitystr.replace_strings(raw, [(hits[0][0], JP_HELLO, "One"),
                                         (hits[1][0], JP_MENU, "Two")])
    assert unitystr.find_jp_strings(out) == []
    assert b"One" in out and b"Two" in out


def test_padding_helper():
    assert [unitystr.padding(n) for n in range(5)] == [0, 3, 2, 1, 0]
