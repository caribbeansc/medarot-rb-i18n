"""Turn a language pack plus the user's romfs into a LayeredFS mod.

Step order is fixed and load-bearing: see ``docs/specs/SPEC-006-build-pipeline.md``.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import extract, ui
from .config import Project
from .lang import LanguagePack
from .patch import StepResult, bundle_labels, fonts, scene_labels, tables, textures

#: In execution order. Names double as the values for ``--only`` / ``--skip``.
STEPS = [
    "tables",
    "fonts",
    "bundle-labels",
    "bundle-textures",
    "scene-labels",
    "scene-textures",
    "sprite-atlas",
]


class BuildError(Exception):
    pass


@dataclass
class BuildReport:
    pack_code: str
    mod_dir: Path
    results: list[StepResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def applied(self) -> int:
        return sum(r.applied for r in self.results)

    @property
    def files(self) -> int:
        return sum(r.files for r in self.results)

    def ok(self) -> bool:
        return self.applied > 0


def _selected(only, skip) -> list[str]:
    chosen = list(STEPS)
    if only:
        unknown = set(only) - set(STEPS)
        if unknown:
            raise BuildError(f"unknown step(s): {', '.join(sorted(unknown))}")
        chosen = [s for s in STEPS if s in set(only)]
    if skip:
        unknown = set(skip) - set(STEPS)
        if unknown:
            raise BuildError(f"unknown step(s): {', '.join(sorted(unknown))}")
        chosen = [s for s in chosen if s not in set(skip)]
    return chosen


def run(project: Project, pack: LanguagePack, *, only=None, skip=None,
        ascii_mode: bool = False, keep: bool = False,
        allow_stale: bool = False) -> BuildReport:
    project.require_romfs()
    steps = _selected(only, skip)

    project.use_base_cache = pack.font.fix_tmp_metrics
    build_root = project.build_lang(pack.code)
    mod_dir = build_root / pack.mod_name
    out_root = mod_dir / "romfs"

    if build_root.exists() and not keep:
        shutil.rmtree(build_root)
    out_root.mkdir(parents=True, exist_ok=True)

    report = BuildReport(pack_code=pack.code, mod_dir=mod_dir)

    if pack.font.fix_tmp_metrics and not project.base_cache.exists():
        report.warnings.append(
            "no prepared cache: Latin text will look cramped in menus. "
            "Run 'mrb prepare' once to fix that.")
    elif project.dump_changed():
        # The base game and the update share a title id, so this is the only way
        # to notice that the cache came from the other one.
        report.warnings.append(
            "the prepared cache and the inventories were built from a different "
            "dump of this title. Run 'mrb extract' and 'mrb prepare' again, or "
            "the mod will mix files from both.")

    ascii_table = pack.ascii_table() if ascii_mode else None
    if ascii_mode and ascii_table is None:
        report.warnings.append(
            f"--ascii asked for, but {pack.code} defines no ascii_fallback map")

    texture_index = None
    if {"bundle-textures"} & set(steps) and pack.deltas():
        texture_index = extract.texture_index(project)

    for step in steps:
        ui.step(f"{step}")
        if step == "tables":
            result = tables.run(project, pack, out_root, ascii_table=ascii_table,
                                allow_stale=allow_stale)
        elif step == "fonts":
            result = fonts.run(project, pack, out_root)
        elif step == "bundle-labels":
            result = bundle_labels.run(project, pack, out_root,
                                       ascii_table=ascii_table)
        elif step == "bundle-textures":
            result = textures.run_bundles(project, pack, out_root,
                                          texture_index=texture_index)
        elif step == "scene-labels":
            result = scene_labels.run(project, pack, out_root,
                                      ascii_table=ascii_table)
        elif step == "scene-textures":
            result = textures.run_scenes(project, pack, out_root)
        elif step == "sprite-atlas":
            result = textures.run_atlas(project, pack, out_root)
        else:  # pragma: no cover - guarded by _selected()
            raise BuildError(f"unknown step {step}")

        report.results.append(result)
        ui.info(result.summary())
        for note in result.notes[:6]:
            ui.detail(note)
        if len(result.notes) > 6:
            ui.detail(f"… and {len(result.notes) - 6} more notes")

    # The prepared cache is part of the mod, not just a place to read from: a
    # bundle that only needed the metric fix is never rewritten by any step above,
    # so without this it would stay out of the mod and the fix would not reach the
    # game (SPEC-006/R-4).
    if pack.font.fix_tmp_metrics and project.base_cache.is_dir():
        carried = StepResult("metrics-cache")
        for path in sorted(project.base_cache.rglob("*")):
            if not path.is_file():
                continue
            dest = out_root / path.relative_to(project.base_cache)
            if dest.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            carried.files += 1
        if carried.files:
            ui.step("metrics-cache")
            ui.info(f"{carried.files} files carried over from the prepared cache")
            report.results.append(carried)

    # Copy the pack's own extras verbatim, if it ships any. They are laid out the
    # way the mod is (``romfs/…``), so they land in the mod directory, not inside
    # ``romfs/``: otherwise the path would be doubled.
    extras = pack.directory / "mod_extras"
    if extras.is_dir():
        copied = 0
        for path in extras.rglob("*"):
            if path.is_file() and not path.name.startswith("."):
                dest = mod_dir / path.relative_to(extras)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest)
                copied += 1
        if copied:
            ui.info(f"mod_extras: {copied} files copied verbatim")

    return report


def describe_mod(mod_dir: Path) -> list[str]:
    """A short listing of what a built mod contains."""
    romfs = mod_dir / "romfs"
    if not romfs.exists():
        return []
    lines = []
    for group, pattern in (
        ("data tables", "Data/StreamingAssets/IdxResData/*.bytes"),
        ("UI bundles", "Data/StreamingAssets/aa/Switch/*.bundle"),
    ):
        count = len(list(romfs.glob(pattern)))
        if count:
            lines.append(f"{count} {group}")
    scenes = [p.name for p in romfs.glob("Data/*")
              if p.is_file() and p.suffix in {"", ".assets"}]
    if scenes:
        lines.append(f"{len(scenes)} scene files ({', '.join(sorted(scenes)[:4])}…)")
    return lines
