"""Check a language pack against every dump you have.

The game exists in four shapes: Kuwagata Ver. and Kabuto Ver., each with and
without the v1.1 update. They share their data tables almost exactly: the update
rewrites fifteen cells and adds nine: so one pack can cover all four, provided it
carries an entry for each wording (SPEC-005/R-9).

Point the suite at as many as you have::

    MEDAROT_ROMFS=/dumps/kuwagata-v1.1 \\
    MEDAROT_EXTRA_ROMFS=/dumps/kuwagata-base,/dumps/kabuto-v1.1,/dumps/kabuto-base \\
    pytest tests/test_dumps.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from medarot import catalog, config, lang
from medarot.formats import idxres

pytestmark = pytest.mark.game

#: Tables a pack may deliberately leave untranslated.
POLICY_TABLES = {"StaffCredits", "SupecialSupporter"}


def dumps() -> list[Path]:
    found = []
    primary = config.load(Path(__file__).resolve().parent.parent)
    if primary.has_romfs():
        found.append(Path(primary.romfs))
    for extra in os.environ.get("MEDAROT_EXTRA_ROMFS", "").split(","):
        extra = extra.strip()
        if extra and config.looks_like_romfs(extra):
            found.append(Path(extra))
    return found


def japanese_cells(romfs: Path) -> dict:
    """``{(table, row, n, sub, col): source text}`` for every translatable cell."""
    out = {}
    for path in sorted((romfs / config.IDXRES_DIR).glob("IdxRes_*.bytes")):
        name = idxres.table_name(path)
        if name in POLICY_TABLES:
            continue
        table = idxres.parse_file(path)
        seen: dict[str, int] = {}
        for row in table.rows:
            occurrence = seen.get(row.key, 0)
            seen[row.key] = occurrence + 1
            for sub_index, sub in enumerate(row.cells):
                for col_index, col in table.string_columns():
                    value = sub[col_index]
                    if catalog.has_source_text(value):
                        out[(name, row.key, occurrence, sub_index, col)] = value
    return out


def pack_index(pack) -> dict:
    """``{(table, row, n, sub, col): {fingerprint: translation}}``"""
    out: dict = {}
    for table in pack.tables():
        for entry in pack.table_catalog(table).entries:
            key = (table, entry["row"], entry.get("n", 0), entry["sub"], entry["col"])
            out.setdefault(key, {})[entry.get("src", "")] = entry.get("t", "")
    return out


@pytest.fixture(scope="module")
def spanish():
    return lang.get(Path(__file__).resolve().parent.parent / "langs", "es")


def test_at_least_one_dump_is_available():
    assert dumps(), "no dump configured (MEDAROT_ROMFS / mrb setup)"


def test_every_dump_is_covered_by_the_spanish_pack(spanish):
    """Every Japanese cell in every dump has a translation written for that wording."""
    index = pack_index(spanish)
    problems = []
    for romfs in dumps():
        release = config.detect_release(romfs)
        label = f"{release[1] if release else romfs.name}"
        missing = 0
        for key, text in japanese_cells(romfs).items():
            variants = index.get(key)
            if not variants or not variants.get(catalog.fingerprint(text)):
                missing += 1
        if missing:
            problems.append(f"{label} ({romfs}): {missing} cells with no usable translation")
    assert not problems, "; ".join(problems)


def test_tables_round_trip_in_every_dump():
    """SPEC-001/R-3 across every version of the game available here."""
    for romfs in dumps():
        bad = [p.name for p in sorted((romfs / config.IDXRES_DIR).glob("*.bytes"))
               if not idxres.roundtrip_ok(p)]
        assert not bad, f"{romfs}: {bad}"


def test_releases_are_recognised():
    """SPEC-006/R-16: each dump identifies itself."""
    for romfs in dumps():
        assert config.detect_release(romfs), f"{romfs}: release not recognised"


def test_dump_fingerprints_differ():
    """Every dump you have must be distinguishable from the others.

    Without the update the two releases are byte-identical bar four files, so this
    only holds because the fingerprint is Unity's build id.
    """
    seen = {}
    for romfs in dumps():
        project = config.load()
        project.romfs = romfs
        fingerprint = project.dump_fingerprint()
        assert fingerprint not in seen, (
            f"{romfs} and {seen[fingerprint]} produce the same fingerprint")
        seen[fingerprint] = romfs
