"""Step 5 — translate text serialized inside the scenes.

The battle screen reads its labels from ``Data/level3`` and
``Data/sharedassets*.assets``, not from bundles, and those ``MonoBehaviour``s
have no usable typetree — so the strings are replaced in the raw object bytes
(SPEC-002).
"""

from __future__ import annotations

from pathlib import Path

from .. import catalog, ui, unity
from ..config import Project
from ..formats import unitystr
from ..lang import LanguagePack
from . import StepResult, apply_ascii, scene_rel, source_for


def run(project: Project, pack: LanguagePack, out_root: Path, *,
        ascii_table=None) -> StepResult:
    result = StepResult("scene-labels")

    translations = pack.label_catalog().by_fingerprint()
    if not translations:
        result.note("no label translations in this pack")
        return result

    scenes = [path.name for path in project.scenes()]
    progress = ui.Progress("scenes", len(scenes))
    for name in scenes:
        relative = scene_rel(name)
        source = source_for(project, out_root, relative)
        if not source.exists():
            progress.advance()
            continue

        env = unity.load(source)
        applied = 0
        for obj in unity.objects(env):
            try:
                raw = obj.get_raw_data()
            except Exception:
                continue
            hits = unitystr.find_jp_strings(raw)
            if not hits:
                continue
            replacements = []
            for offset, text in hits:
                entry = translations.get(catalog.fingerprint(text))
                if entry and entry.get("t"):
                    replacements.append(
                        (offset, text, apply_ascii(entry["t"], ascii_table)))
                else:
                    result.skipped += 1
            if replacements:
                obj.set_raw_data(unitystr.replace_strings(raw, replacements))
                applied += len(replacements)

        if not applied:
            progress.advance(name)
            continue

        dest = out_root / relative
        unity.save(env, dest)

        # read back: nothing translatable should be left (SPEC-006/R-5)
        leftover = 0
        check = unity.load(dest)
        for obj in unity.objects(check):
            try:
                raw = obj.get_raw_data()
            except Exception:
                continue
            for _, text in unitystr.find_jp_strings(raw):
                entry = translations.get(catalog.fingerprint(text))
                if entry and entry.get("t"):
                    leftover += 1
        if leftover:
            raise RuntimeError(f"{name}: {leftover} translated strings did not stick")

        result.applied += applied
        result.files += 1
        ui.detail(f"{name}: {applied} strings")
        progress.advance(name)
    progress.done(f"{result.applied} strings in {result.files} scene files")
    return result
