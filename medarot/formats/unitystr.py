"""Find and replace Unity serialized strings inside raw object bytes.

The scene ``MonoBehaviour``s carry no usable typetree, so their labels have to be
patched at the byte level. See ``docs/specs/SPEC-002-unity-strings.md``.

A serialized string is::

    int32 length | length bytes of UTF-8 | zero padding to a multiple of 4
"""

from __future__ import annotations

import re
import struct

#: Kana and CJK ideographs: what "the text is still Japanese" means here.
JP_RE = re.compile(r"[぀-ヿ㐀-鿿]")
CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

#: UTF-8 byte sequences for kana/CJK: E3 81-BF xx, or E4-E9 xx xx.
JP_BYTES_RE = re.compile(rb"(?:\xe3[\x81-\xbf][\x80-\xbf]|[\xe4-\xe9][\x80-\xbf][\x80-\xbf])")

MAX_LEN = 8192
MIN_LEN = 2


def padding(length: int) -> int:
    return (-length) % 4


def find_jp_strings(raw: bytes) -> list[tuple[int, str]]:
    """Return ``[(offset_of_length_prefix, text)]`` for Japanese strings.

    Starts from the Japanese bytes and walks backwards looking for a length
    prefix that fits exactly (SPEC-002/R-3), so it does not depend on where the
    object begins.
    """
    size = len(raw)
    found: dict[int, str] = {}
    spans: list[tuple[int, int]] = []

    for match in JP_BYTES_RE.finditer(raw):
        pos = match.start()
        if any(start <= pos < end for start, end in spans):
            continue
        for text_start in range(pos, max(-1, pos - MAX_LEN) - 1, -1):
            offset = text_start - 4
            if offset < 0:
                break
            length = struct.unpack_from("<i", raw, offset)[0]
            end = text_start + length
            if length < MIN_LEN or length > MAX_LEN or end > size:
                continue
            if end <= pos:  # the Japanese bytes would fall outside this string
                continue
            pad = padding(length)
            if end + pad > size or raw[end:end + pad] != b"\x00" * pad:
                continue
            try:
                text = raw[text_start:end].decode("utf-8")
            except UnicodeDecodeError:
                continue
            if not JP_RE.search(text) or CTRL_RE.search(text):
                continue
            found[offset] = text
            spans.append((offset, end))
            break
    return sorted(found.items())


def replace_strings(raw: bytes, replacements) -> bytes:
    """Apply ``[(offset, old_text, new_text)]`` to a raw object buffer.

    Verifies the stored length *and* the stored bytes before writing
    (SPEC-002/R-5): a mismatch means the offset is stale and patching would
    corrupt the object.
    """
    out = bytearray()
    pos = 0
    for offset, old, new in sorted(replacements):
        old_raw = old.encode("utf-8")
        stored = struct.unpack_from("<i", raw, offset)[0]
        if stored != len(old_raw):
            raise ValueError(
                f"unexpected length at offset {offset}: {stored} != {len(old_raw)}"
            )
        if raw[offset + 4:offset + 4 + len(old_raw)] != old_raw:
            raise ValueError(f"unexpected text at offset {offset}")
        out += raw[pos:offset]
        new_raw = new.encode("utf-8")
        out += struct.pack("<i", len(new_raw)) + new_raw + b"\x00" * padding(len(new_raw))
        pos = offset + 4 + len(old_raw) + padding(len(old_raw))
    out += raw[pos:]
    return bytes(out)


def encode_string(text: str) -> bytes:
    """Serialize one string the way Unity does (useful in tests)."""
    raw = text.encode("utf-8")
    return struct.pack("<i", len(raw)) + raw + b"\x00" * padding(len(raw))
