"""Backup handling: the parts that need no game files or keys.

The end-to-end extraction (hactool + a real dump) is covered by the 'game'
suite; here we pin the pure helpers that decide file types and dig title keys
out of tickets and title.keys files.
"""

from __future__ import annotations

from medarot import backup


def test_is_backup_recognises_every_format():
    for name in ("game.xci", "game.NSP", "game.xcz", "game.nsz", "GAME.XCI"):
        assert backup.is_backup(name), name


def test_is_backup_rejects_folders_and_archives():
    for name in ("romfs", "romfs/", "mod.zip", "prod.keys", "boot.config"):
        assert not backup.is_backup(name), name


def test_titlekey_from_ticket_reads_offset_0x180(tmp_path):
    ticket = tmp_path / "title.tik"
    key = bytes(range(16))
    ticket.write_bytes(b"\x00" * 0x180 + key + b"\x00" * 0x20)
    assert backup._titlekey_from_ticket(ticket) == key.hex()


def test_titlekey_from_ticket_ignores_a_truncated_file(tmp_path):
    ticket = tmp_path / "short.tik"
    ticket.write_bytes(b"\x00" * 0x100)
    assert backup._titlekey_from_ticket(ticket) is None


def test_titlekey_from_file_matches_rights_id_case_insensitively(tmp_path):
    keys = tmp_path / "title.keys"
    keys.write_text(
        "0100CB6024FF88000000000000000016 = 716f5b00936dd8158156004c2df65fc6\n"
        "somethingelse = deadbeef\n",
        encoding="utf-8")
    got = backup._titlekey_from_file(keys, "0100cb6024ff88000000000000000016")
    assert got == "716f5b00936dd8158156004c2df65fc6"


def test_titlekey_from_file_returns_none_when_absent(tmp_path):
    keys = tmp_path / "title.keys"
    keys.write_text("aaaa = bbbb\n", encoding="utf-8")
    assert backup._titlekey_from_file(keys, "ffff") is None
    assert backup._titlekey_from_file(None, "ffff") is None


def test_keys_find_prefers_an_explicit_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("MEDAROT_KEYS", raising=False)
    (tmp_path / "prod.keys").write_text("k", encoding="utf-8")
    found = backup.Keys.find(tmp_path)
    assert found is not None
    assert found.prod == tmp_path / "prod.keys"
    assert found.title is None  # no title.keys next to it
