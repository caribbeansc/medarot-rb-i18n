"""Step 1: translate the IdxRes data tables.

These are loose files in the romfs, so this step alone already produces a working
mod: no Unity bundle is involved.
"""

from __future__ import annotations

from pathlib import Path

from .. import catalog, ui
from ..config import Project
from ..formats import idxres
from ..lang import LanguagePack
from . import StepResult, apply_ascii, table_rel


def run(project: Project, pack: LanguagePack, out_root: Path, *,
        ascii_table=None, allow_stale: bool = False,
        source_map: dict | None = None) -> StepResult:
    result = StepResult("tables")
    source_map = source_map or {}

    for table_name in pack.tables():
        cat = pack.table_catalog(table_name)
        # position -> {fingerprint: entry}. A position can carry more than one
        # entry when the game's own text changed between versions.
        wanted: dict[tuple, dict] = {}
        for entry in cat.entries:
            if entry.get("t"):
                wanted.setdefault(catalog.cell_position(entry), {})[
                    entry.get("src", "")] = entry
        if not wanted:
            continue

        relative = table_rel(table_name)
        source = project.require_romfs() / relative
        if not source.exists():
            result.skipped += len(wanted)
            result.note(f"{table_name}: not in this dump, skipped")
            continue

        raw = source.read_bytes()
        table = idxres.parse(raw)
        if idxres.build(table) != raw:
            result.skipped += len(wanted)
            result.note(f"{table_name}: round-trip mismatch, skipped")
            continue

        rows: dict[str, list] = {}
        for row in table.rows:
            rows.setdefault(row.key, []).append(row)

        applied = 0
        for (row_key, occurrence, sub_index, column), variants in wanted.items():
            candidates = rows.get(row_key)
            if not candidates or occurrence >= len(candidates):
                result.skipped += 1
                result.note(f"{table_name}: row {row_key!r} is gone")
                continue
            row = candidates[occurrence]
            try:
                col_index = table.column_index(column)
            except KeyError:
                result.skipped += 1
                result.note(f"{table_name}: column {column!r} is gone")
                continue
            if sub_index >= len(row.cells):
                result.skipped += 1
                result.note(f"{table_name}: {row_key}[{sub_index}] is gone")
                continue

            current = row.cells[sub_index][col_index]
            entry = variants.get(catalog.fingerprint(current))
            if entry is None:
                # None of the translations was written for the text this dump
                # actually holds.
                if not allow_stale:
                    result.skipped += 1
                    result.note(
                        f"{table_name}/{row_key}/{column}: this dump has different "
                        f"text (no matching translation), skipped: "
                        f"--allow-stale forces it")
                    continue
                entry = next(iter(variants.values()))
                result.note(f"{table_name}/{row_key}/{column}: stale key applied")

            row.cells[sub_index][col_index] = apply_ascii(entry["t"], ascii_table)
            applied += 1

        if not applied:
            continue

        dest = out_root / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(idxres.build(table))

        # read back what we wrote (SPEC-006/R-5)
        verify = idxres.parse_file(dest)
        assert len(verify.rows) == len(table.rows), f"{table_name}: row count changed"

        result.applied += applied
        result.files += 1
        ui.detail(f"{table_name}: {applied} strings")

    return result
