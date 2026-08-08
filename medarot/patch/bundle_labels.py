"""Step 3 — translate TextMeshPro labels serialized inside UI bundles.

Those labels are not in the data tables: they are baked into prefabs, so they are
addressed by ``(bundle, path_id, field)`` from the inventory built by
``mrb extract`` and translated by fingerprint (SPEC-005).
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .. import catalog, extract, ui, unity
from ..config import Project
from ..lang import LanguagePack
from . import StepResult, apply_ascii, bundle_rel, source_for


def run(project: Project, pack: LanguagePack, out_root: Path, *,
        ascii_table=None) -> StepResult:
    result = StepResult("bundle-labels")

    inventory = extract.read_inventory(project, "bundle_labels")
    if inventory is None:
        result.note("no bundle inventory yet — run 'mrb extract'")
        return result

    translations = pack.label_catalog().by_fingerprint()
    if not translations:
        result.note("no label translations in this pack")
        return result

    # bundle -> {path_id: (field, new text)}
    plan: dict[str, dict[int, tuple[str, str]]] = defaultdict(dict)
    missing = set()
    for record in inventory:
        entry = translations.get(catalog.fingerprint(record["text"]))
        if not entry or not entry.get("t"):
            missing.add(record["text"])
            continue
        plan[record["bundle"]][record["pid"]] = (
            record["field"], apply_ascii(entry["t"], ascii_table))

    if missing:
        result.skipped += len(missing)
        result.note(f"{len(missing)} distinct labels have no translation yet")

    progress = ui.Progress("bundles", len(plan), every=5)
    for bundle_name, patches in sorted(plan.items()):
        relative = bundle_rel(bundle_name)
        source = source_for(project, out_root, relative)
        if not source.exists():
            result.skipped += len(patches)
            progress.advance()
            continue

        env = unity.load(source)
        applied = 0
        for obj in unity.objects(env, "MonoBehaviour"):
            patch = patches.get(obj.path_id)
            if not patch:
                continue
            field_name, text = patch
            tree = unity.typetree(obj)
            if tree is None or field_name not in tree:
                result.skipped += 1
                continue
            tree[field_name] = text
            obj.save_typetree(tree)
            applied += 1

        if not applied:
            progress.advance()
            continue

        dest = out_root / relative
        unity.save(env, dest)

        # read back (SPEC-006/R-5)
        verified = 0
        check = unity.load(dest)
        for obj in unity.objects(check, "MonoBehaviour"):
            patch = patches.get(obj.path_id)
            if not patch:
                continue
            tree = unity.typetree(obj)
            if tree and tree.get(patch[0]) == patch[1]:
                verified += 1
        if verified != applied:
            raise RuntimeError(
                f"{bundle_name}: wrote {applied} labels but read back {verified}")

        result.applied += applied
        result.files += 1
        progress.advance(bundle_name[:40])
    progress.done(f"{result.applied} labels in {result.files} bundles")
    return result
