"""Read the user's own dump: tables, labels, texture inventory, PNG export.

Everything this module writes lands under ``work/``, which is gitignored: it is
the one place where source text and translation sit side by side, so a human can
actually translate (SPEC-005/R-7).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import catalog, ui, unity
from .config import Project
from .formats import idxres, unitystr

#: Fields of a TextMeshPro component that hold user-visible text.
TEXT_FIELDS = ("m_text",)


class ExtractError(Exception):
    pass


# ------------------------------------------------------------------ tables --

@dataclass
class Cell:
    table: str
    row: str
    sub: int
    col: str
    text: str
    #: Ordinal of this row among the rows sharing its key (SPEC-001/R-6).
    n: int = 0


def read_tables(project: Project, *, dump_raw: bool = True,
                verify: bool = True) -> dict[str, list[Cell]]:
    """Parse every IdxRes table and return its Japanese string cells.

    Each table is round-trip checked before being trusted (SPEC-001/R-3): if
    rebuilding it is not byte-identical, the table is skipped loudly rather than
    risking a corrupt mod.
    """
    files = sorted(project.tables_dir.glob("IdxRes_*.bytes"))
    if not files:
        raise ExtractError(f"no IdxRes_*.bytes in {project.tables_dir}")

    found: dict[str, list[Cell]] = {}
    progress = ui.Progress("tables", len(files), every=10)
    for path in files:
        name = idxres.table_name(path)
        raw = path.read_bytes()
        table = idxres.parse(raw)
        if verify and idxres.build(table) != raw:
            ui.fail(f"{path.name}: round-trip mismatch, skipped (report this!)")
            continue
        if dump_raw:
            _dump_raw(project, name, table)
        seen_keys: dict[str, int] = {}
        cells = []
        for row in table.rows:
            occurrence = seen_keys.get(row.key, 0)
            seen_keys[row.key] = occurrence + 1
            for sub_index, sub in enumerate(row.cells):
                for col_index, col_name in table.string_columns():
                    value = sub[col_index]
                    if catalog.has_source_text(value):
                        cells.append(Cell(name, row.key, sub_index, col_name,
                                          value, occurrence))
        if cells:
            found[name] = cells
        progress.advance()
    progress.done(f"{len(files)} tables parsed, {len(found)} with source text")
    return found


def _dump_raw(project: Project, name: str, table: idxres.Table) -> None:
    """A faithful JSON dump of a table, for looking things up by hand."""
    doc = {
        "bytes_path": table.bytes_path,
        "xlsx_path": table.xlsx_path,
        "sheet": table.sheet,
        "start_cell": table.start_cell,
        "columns": [{"name": c.name, "type": c.type,
                     "type_name": idxres.TYPE_NAMES.get(c.type, "?")}
                    for c in table.columns],
        "rows": [{"key": r.key, "cells": r.cells} for r in table.rows],
    }
    project.raw_dir.mkdir(parents=True, exist_ok=True)
    (project.raw_dir / f"{name}.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


# ------------------------------------------------------------------ labels --

def scan_bundle_labels(project: Project) -> tuple[list[dict], list[dict]]:
    """Scan every bundle for Japanese text.

    Returns ``(labels, other)``:

    * ``labels`` — TextMeshPro text fields, which the build can patch:
      ``{"bundle", "pid", "field", "text"}``
    * ``other`` — any other Japanese string found in a typetree, reported for
      research only. Patching those blind would be reckless, but knowing they
      exist is useful.
    """
    bundles = project.bundles()
    labels: list[dict] = []
    other: list[dict] = []
    progress = ui.Progress("bundles", len(bundles), every=25)
    for path in bundles:
        try:
            env = unity.load(path)
        except Exception as exc:
            ui.warn(f"{path.name}: cannot open ({exc})")
            progress.advance()
            continue
        for obj in unity.objects(env, "MonoBehaviour", "TextAsset", "GameObject"):
            tree = unity.typetree(obj)
            if not tree:
                continue
            for field_path, value in _walk_strings(tree):
                if not catalog.has_source_text(value):
                    continue
                record = {"bundle": path.name, "pid": obj.path_id,
                          "field": field_path.lstrip("."), "text": value}
                if field_path.lstrip(".") in TEXT_FIELDS:
                    labels.append(record)
                else:
                    other.append(record)
        progress.advance(path.name[:40])
    progress.done(f"{len(labels)} text labels, {len(other)} other strings")
    return labels, other


def _walk_strings(node, path: str = ""):
    """Yield ``(dotted path, string)`` for every non-empty string in a typetree."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk_strings(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node[:512]):
            yield from _walk_strings(value, f"{path}[{index}]")
    elif isinstance(node, str) and node:
        yield path, node


def scan_scene_labels(project: Project) -> list[dict]:
    """Scan scene containers for Japanese strings in raw object bytes."""
    scenes = project.scenes()
    out: list[dict] = []
    progress = ui.Progress("scenes", len(scenes))
    for path in scenes:
        try:
            env = unity.load(path)
        except Exception as exc:
            ui.warn(f"{path.name}: cannot open ({exc})")
            progress.advance()
            continue
        for obj in unity.objects(env):
            try:
                raw = obj.get_raw_data()
            except Exception:
                continue
            for _, text in unitystr.find_jp_strings(raw):
                out.append({"file": path.name, "pid": obj.path_id,
                            "type": obj.type.name, "text": text})
        progress.advance(path.name)
    progress.done(f"{len(out)} strings in scenes")
    return out


# ---------------------------------------------------------------- textures --

def texture_index(project: Project, *, refresh: bool = False) -> dict:
    """Texture name -> containers it lives in, cached under ``work/``.

    Many textures exist twice: once in a bundle and once inside
    ``sharedassets*.assets``. The battle scene uses the ``sharedassets`` copy, so
    both have to be patched, and both have to be findable.
    """
    cache = project.inventory_dir / "textures.json"
    if cache.exists() and not refresh:
        return json.loads(cache.read_text(encoding="utf-8"))

    from .formats.switchtex import format_name, is_affected

    index: dict[str, dict] = {}
    containers = [("bundle", p) for p in project.bundles()]
    containers += [("scene", p) for p in project.scenes()]
    progress = ui.Progress("scanning textures", len(containers), every=25)
    for kind, path in containers:
        try:
            env = unity.load(path)
        except Exception:
            progress.advance()
            continue
        for obj, data in unity.textures(env):
            name = data.m_Name
            if not name:
                continue
            entry = index.setdefault(name, {
                "name": name,
                "group": unity.bundle_group(path) if kind == "bundle" else "scene",
                "width": int(data.m_Width),
                "height": int(data.m_Height),
                "format": format_name(data.m_TextureFormat),
                "format_id": int(data.m_TextureFormat),
                "containers": [],
            })
            try:
                entry.setdefault("swizzle_bug", bool(is_affected(obj, data)))
            except Exception:
                pass
            entry["containers"].append(f"{kind}:{path.name}")
        progress.advance(path.name[:40])
    progress.done(f"{len(index)} textures indexed")

    project.inventory_dir.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    return index


def export_textures(project: Project, *, names=None, groups=None,
                    scenes: bool = True) -> int:
    """Export Texture2D assets to ``work/assets/<group>/<name>.png``.

    This is how a translator gets at baked-in text: export, edit the PNG in any
    image editor, then ``mrb textures --import`` turns it back into a delta.
    """
    wanted = set(names or [])
    containers = [("bundle", p) for p in project.bundles()]
    if scenes:
        containers += [("scene", p) for p in project.scenes()]

    written = 0
    progress = ui.Progress("exporting", len(containers), every=25)
    for kind, path in containers:
        group = unity.bundle_group(path) if kind == "bundle" else "scene"
        if groups and group not in groups:
            progress.advance()
            continue
        try:
            env = unity.load(path)
        except Exception:
            progress.advance()
            continue
        seen: set[str] = set()
        for _, data in unity.textures(env):
            name = data.m_Name
            if not name or (wanted and name not in wanted):
                continue
            if name in seen:
                continue
            seen.add(name)
            dest = project.assets_dir / group / f"{name}.png"
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                data.image.save(dest)
            except Exception as exc:
                ui.warn(f"{name}: cannot decode ({exc})")
                continue
            written += 1
        progress.advance(path.name[:40])
    progress.done(f"{written} PNGs under {project.assets_dir}")
    return written


def find_texture(project: Project, name: str):
    """Load one texture out of the user's dump, as a PIL image.

    Prefers the scene copy, because that is what the battle screens draw.
    """
    index = texture_index(project)
    entry = index.get(name)
    if not entry:
        return None
    containers = sorted(entry["containers"], key=lambda c: 0 if c.startswith("scene:") else 1)
    for container in containers:
        kind, _, filename = container.partition(":")
        path = (project.data_dir / filename if kind == "scene"
                else project.bundles_dir / filename)
        if not path.exists():
            continue
        try:
            env = unity.load(path)
        except Exception:
            continue
        for _, data in unity.textures(env):
            if data.m_Name == name:
                try:
                    return data.image.convert("RGBA")
                except Exception:
                    continue
    return None


# -------------------------------------------------------------- inventories --

def inventory_path(project: Project, name: str) -> Path:
    return project.inventory_dir / f"{name}.json"


def write_inventory(project: Project, name: str, data) -> Path:
    project.inventory_dir.mkdir(parents=True, exist_ok=True)
    path = inventory_path(project, name)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def read_inventory(project: Project, name: str):
    path = inventory_path(project, name)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def refresh_all(project: Project, *, tables: bool = True, bundles: bool = True,
                scenes: bool = True) -> dict:
    """Rebuild the inventories the build and the editor need."""
    summary = {}
    project.record_dump()
    if tables:
        ui.step("Reading data tables")
        cells = read_tables(project)
        write_inventory(project, "tables", {
            name: [{"row": c.row, "n": c.n, "sub": c.sub, "col": c.col,
                    "text": c.text} for c in items]
            for name, items in cells.items()
        })
        summary["tables"] = sum(len(v) for v in cells.values())
    if bundles:
        ui.step("Scanning bundles for text (this takes a few minutes)")
        labels, other = scan_bundle_labels(project)
        write_inventory(project, "bundle_labels", labels)
        write_inventory(project, "other_strings", other)
        summary["bundle_labels"] = len(labels)
    if scenes:
        ui.step("Scanning scenes for text")
        scene_labels = scan_scene_labels(project)
        write_inventory(project, "scene_labels", scene_labels)
        summary["scene_labels"] = len(scene_labels)
    return summary
