"""Round-trip a translation through a spreadsheet.

Most translators would rather work in LibreOffice or Excel than in JSON, so the
working copy can be exported to one CSV and read back from it. The file is
written with a UTF-8 BOM so Excel opens it as Unicode without a dialog.

Only ``work/`` is touched: the CSV holds the game's source text, so it is a local
file and must not be committed (SPEC-005/R-7).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from . import catalog
from .workspace import Workspace

COLUMNS = ["where", "key", "source", "translation", "note"]

#: Separator inside the ``key`` column. The game's row keys and column names
#: are identifiers, so this never occurs inside one.
KEY_SEP = "|"


class CsvError(Exception):
    pass


def _key_of(where: str, entry: dict) -> str:
    if where == "labels":
        return entry["src"]
    return KEY_SEP.join((entry["row"], str(entry.get("n", 0)),
                         str(entry["sub"]), entry["col"], entry.get("src", "")))


def _parse_key(where: str, key: str):
    if where == "labels":
        return key
    parts = key.split(KEY_SEP)
    if len(parts) != 5 or not (parts[1].isdigit() and parts[2].isdigit()):
        raise CsvError(f"malformed key {key!r} for table {where}")
    return catalog.cell_key(parts[0], int(parts[2]), parts[3],
                            int(parts[1])) + (parts[4],)


@dataclass
class CsvReport:
    rows: int = 0
    applied: int = 0
    unchanged: int = 0
    unknown: int = 0


def export(workspace: Workspace, dest, *, pending_only: bool = False) -> int:
    """Write the working copy to a CSV. Returns the number of rows."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    with dest.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for table in workspace.tables():
            for entry in workspace.table_catalog(table).entries:
                if pending_only and entry.get("t"):
                    continue
                writer.writerow([table, _key_of(table, entry), entry.get("jp", ""),
                                 entry.get("t", ""), entry.get("note", "")])
                rows += 1
        for entry in workspace.label_catalog().entries:
            if pending_only and entry.get("t"):
                continue
            writer.writerow(["labels", entry["src"], entry.get("jp", ""),
                             entry.get("t", ""), entry.get("note", "")])
            rows += 1
    return rows


def import_csv(workspace: Workspace, source) -> CsvReport:
    """Read translations back from a CSV into the working copy."""
    source = Path(source)
    if not source.exists():
        raise CsvError(f"{source}: not found")

    report = CsvReport()
    # group by file so each catalog is written once
    updates: dict[str, dict] = {}
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in ("where", "key", "translation") if c not in (reader.fieldnames or [])]
        if missing:
            raise CsvError(f"{source}: missing column(s) {', '.join(missing)}")
        for row in reader:
            report.rows += 1
            where = (row.get("where") or "").strip()
            key = row.get("key") or ""
            translation = (row.get("translation") or "").strip()
            if not where or not key or not translation:
                continue
            updates.setdefault(where, {})[_parse_key(where, key)] = (
                translation, (row.get("note") or "").strip())

    for where, values in updates.items():
        if where == "labels":
            cat = workspace.label_catalog()
            path = workspace.labels_file
            kind = catalog.KIND_LABELS
        else:
            path = workspace.table_file(where)
            if not path.exists():
                report.unknown += len(values)
                continue
            cat = workspace.table_catalog(where)
            kind = catalog.KIND_IDXRES
        touched = False
        for entry in cat.entries:
            pair = values.pop(catalog.entry_key(entry, kind), None)
            if pair is None:
                continue
            translation, note = pair
            if entry.get("t") == translation:
                report.unchanged += 1
                continue
            entry["t"] = translation
            if note:
                entry["note"] = note
            report.applied += 1
            touched = True
        report.unknown += len(values)
        if touched:
            cat.save(path)
    return report
