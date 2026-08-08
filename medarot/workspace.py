"""The bilingual working copy: ``work/lang/<code>/``.

``langs/`` is publishable and holds no source text. ``work/`` is local, gitignored
and holds the original next to the translation, which is what a human needs in
order to translate. ``refresh`` builds the working copy from the user's dump;
``sync`` promotes it back, dropping the source text.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import catalog, extract, ui
from .config import Project
from .lang import LanguagePack

WORK_HELP = (
    "Fill in the 't' fields. 'jp' is the game's own text, read from your dump; "
    "it is never committed. Run: mrb sync <lang>"
)


class WorkspaceError(Exception):
    pass


@dataclass
class Workspace:
    project: Project
    pack: LanguagePack

    # ---------------------------------------------------------------- paths --
    @property
    def root(self) -> Path:
        return self.project.work_lang(self.pack.code)

    @property
    def idxres_dir(self) -> Path:
        return self.root / "idxres"

    @property
    def labels_file(self) -> Path:
        return self.root / "labels.json"

    def table_file(self, table: str) -> Path:
        return self.idxres_dir / f"{table}.json"

    def tables(self) -> list[str]:
        if not self.idxres_dir.is_dir():
            return []
        return sorted(p.stem for p in self.idxres_dir.glob("*.json"))

    def exists(self) -> bool:
        return self.labels_file.exists() or bool(self.tables())

    # ------------------------------------------------------------ catalogs --
    def table_catalog(self, table: str) -> catalog.Catalog:
        return catalog.Catalog.load(self.table_file(table), catalog.KIND_IDXRES)

    def label_catalog(self) -> catalog.Catalog:
        return catalog.Catalog.load(self.labels_file, catalog.KIND_LABELS)

    def source_map(self) -> dict[str, str]:
        """Fingerprint -> original text, for validation and staleness checks."""
        out = {}
        for table in self.tables():
            for entry in self.table_catalog(table).entries:
                if entry.get("jp"):
                    out[entry["src"]] = entry["jp"]
        for entry in self.label_catalog().entries:
            if entry.get("jp"):
                out[entry["src"]] = entry["jp"]
        return out

    # ------------------------------------------------------------- refresh --
    def refresh(self) -> dict:
        """(Re)build the working copy from the inventories under ``work/``.

        Existing translations are preserved: a value already present in the work
        file wins, then the published pack fills the rest. Nothing is ever
        overwritten with an empty string.
        """
        tables = extract.read_inventory(self.project, "tables")
        if tables is None:
            raise WorkspaceError(
                "No inventory yet. Run:  mrb extract   (reads your own dump)")

        counts = {"tables": 0, "entries": 0, "kept": 0, "labels": 0}
        self.idxres_dir.mkdir(parents=True, exist_ok=True)

        for table, cells in sorted(tables.items()):
            fresh = catalog.Catalog(kind=catalog.KIND_IDXRES,
                                    meta={"table": table, "_help": WORK_HELP})
            fresh.entries = [
                catalog.idxres_entry(c["row"], c["sub"], c["col"], c["text"],
                                     n=c.get("n", 0))
                for c in cells
            ]
            kept = fresh.merge_from(self.table_catalog(table))
            kept += fresh.merge_from(self.pack.table_catalog(table))
            problems = fresh.check_collisions()
            if problems:
                raise WorkspaceError(f"{table}: " + "; ".join(problems))
            fresh.save(self.table_file(table))
            counts["tables"] += 1
            counts["entries"] += len(fresh.entries)
            counts["kept"] += kept

        counts["labels"] = self._refresh_labels()
        return counts

    def _refresh_labels(self) -> int:
        bundle_labels = extract.read_inventory(self.project, "bundle_labels") or []
        scene_labels = extract.read_inventory(self.project, "scene_labels") or []

        occurrences: dict[str, dict] = {}
        for record in bundle_labels:
            slot = occurrences.setdefault(record["text"], {"seen": 0, "where": set()})
            slot["seen"] += 1
            slot["where"].add("bundle")
        for record in scene_labels:
            slot = occurrences.setdefault(record["text"], {"seen": 0, "where": set()})
            slot["seen"] += 1
            slot["where"].add(f"scene:{record['file']}")

        fresh = catalog.Catalog(kind=catalog.KIND_LABELS, meta={"_help": WORK_HELP})
        for text in sorted(occurrences):
            entry = catalog.label_entry(text)
            entry["seen"] = occurrences[text]["seen"]
            entry["where"] = sorted(occurrences[text]["where"])
            fresh.entries.append(entry)

        fresh.merge_from(self.label_catalog())
        fresh.merge_from(self.pack.label_catalog())
        problems = fresh.check_collisions()
        if problems:
            raise WorkspaceError("labels: " + "; ".join(problems))
        fresh.save(self.labels_file)
        return len(fresh.entries)

    # ---------------------------------------------------------------- sync --
    def sync(self) -> dict:
        """Promote the working copy into the publishable pack.

        Entries in the pack that the current dump does not contain are kept, so a
        user with a different version of the game cannot delete other people's
        work by syncing.
        """
        if not self.exists():
            raise WorkspaceError(
                f"nothing to sync: {self.root} is empty (run mrb extract first)")

        counts = {"tables": 0, "translations": 0, "orphans": 0}
        self.pack.idxres_dir.mkdir(parents=True, exist_ok=True)

        for table in self.tables():
            work = self.table_catalog(table)
            published = self.pack.table_catalog(table)
            merged, orphans = _merge_for_publish(work, published, catalog.KIND_IDXRES)
            merged.meta = {"table": table}
            merged.save(self.pack.table_file(table), strip_source=True)
            counts["tables"] += 1
            counts["translations"] += sum(1 for e in merged.entries if e.get("t"))
            counts["orphans"] += orphans

        work_labels = self.label_catalog()
        published_labels = self.pack.label_catalog()
        merged, orphans = _merge_for_publish(work_labels, published_labels,
                                            catalog.KIND_LABELS)
        merged.meta = {}
        merged.save(self.pack.labels_file, strip_source=True)
        counts["translations"] += sum(1 for e in merged.entries if e.get("t"))
        counts["orphans"] += orphans

        leftovers = catalog.scan_tree_for_source_text(self.pack.directory)
        if leftovers:
            raise WorkspaceError(
                "refusing to publish source text (SPEC-005/R-4) in: "
                + ", ".join(leftovers))
        return counts

    # ------------------------------------------------------------- editing --
    def pending(self, table: str | None = None) -> list[tuple[str, dict]]:
        """``[(where, entry)]`` for entries that still need a translation."""
        out = []
        tables = [table] if table else self.tables()
        for name in tables:
            for entry in self.table_catalog(name).untranslated():
                out.append((name, entry))
        if not table:
            for entry in self.label_catalog().untranslated():
                out.append(("labels", entry))
        return out

    def set_translation(self, where: str, key, value: str) -> bool:
        """Write one translation into the working copy."""
        if where == "labels":
            cat = self.label_catalog()
            path = self.labels_file
            kind = catalog.KIND_LABELS
        else:
            cat = self.table_catalog(where)
            path = self.table_file(where)
            kind = catalog.KIND_IDXRES
        for entry in cat.entries:
            if catalog.entry_key(entry, kind) == key:
                entry["t"] = value
                cat.save(path)
                return True
        return False

    def stats(self) -> dict:
        translated = total = 0
        for table in self.tables():
            done, count = self.table_catalog(table).stats()
            translated += done
            total += count
        label_done, label_total = self.label_catalog().stats()
        return {
            "text_translated": translated + label_done,
            "text_total": total + label_total,
        }


def _merge_for_publish(work: catalog.Catalog, published: catalog.Catalog,
                       kind: str) -> tuple[catalog.Catalog, int]:
    """Work entries first, then published entries the dump does not know about."""
    merged = catalog.Catalog(kind=kind)
    seen = set()
    for entry in work.entries:
        key = catalog.entry_key(entry, kind)
        seen.add(key)
        out = {k: v for k, v in entry.items() if k not in {"jp", "seen", "where"}}
        merged.entries.append(out)
    orphans = 0
    for entry in published.entries:
        key = catalog.entry_key(entry, kind)
        if key in seen or not entry.get("t"):
            continue
        merged.entries.append(dict(entry))
        orphans += 1
    return merged, orphans


def ensure(project: Project, pack: LanguagePack) -> Workspace:
    return Workspace(project=project, pack=pack)


def report(counts: dict) -> None:
    for key in ("tables", "entries", "labels", "translations", "kept", "orphans"):
        if key in counts:
            ui.info(f"{key}: {counts[key]}")
