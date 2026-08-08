"""Step 2 — make the game's fonts able to draw the target language.

The two main fonts (FOT-CometStd-B, FOT-RodinPro-DB) have no accented glyphs, but
other fonts shipped in the same bundle do. TextMeshPro resolves a missing glyph
through a fallback chain, so a pack lists the fallback fonts it needs **by name**
and this step wires them in (SPEC-004/R-6).

It also neutralizes negative kerning pairs when the pack asks for it: those pairs
were tuned for Japanese, where no Latin pair ever occurred, and they overlap
Latin letters badly ("Bullet" rendered as "Bulet").
"""

from __future__ import annotations

from pathlib import Path

from .. import ui, unity
from ..config import BUNDLE_DIR, Project
from ..lang import LanguagePack
from . import StepResult, bundle_rel, source_for

FALLBACK_TABLE = "m_FallbackFontAssetTable"
GLOBAL_FALLBACKS = "m_fallbackFontAssets"
SETTINGS_NAME = "TMP Settings"


def _reference(path_id: int) -> dict:
    return {"m_FileID": 0, "m_PathID": path_id}


def _drop_negative_kerning(tree) -> bool:
    table = tree.get("m_FontFeatureTable")
    if not isinstance(table, dict):
        return False
    records = table.get("m_GlyphPairAdjustmentRecords")
    if not records:
        return False
    touched = False
    for record in records:
        for side in ("m_FirstAdjustmentRecord", "m_SecondAdjustmentRecord"):
            values = record.get(side, {}).get("m_GlyphValueRecord")
            if isinstance(values, dict) and values.get("m_XAdvance", 0) < 0:
                values["m_XAdvance"] = 0.0
                touched = True
    return touched


def run(project: Project, pack: LanguagePack, out_root: Path) -> StepResult:
    result = StepResult("fonts")
    font_config = pack.font
    if not font_config.fallbacks and not font_config.neutralize_kerning:
        result.note("this pack needs no font changes")
        return result

    bundles = project.font_bundles()
    if not bundles:
        result.note(f"no {BUNDLE_DIR}/font_assets_all_*.bundle in this dump")
        return result

    for bundle in bundles:
        relative = bundle_rel(bundle.name)
        env = unity.load(source_for(project, out_root, relative))

        # name -> path_id for every font asset in the bundle
        fonts: dict[str, int] = {}
        trees: dict[int, dict] = {}
        for obj in unity.objects(env, "MonoBehaviour"):
            tree = unity.typetree(obj)
            if tree is None:
                continue
            trees[obj.path_id] = tree
            name = tree.get("m_Name", "")
            if name and FALLBACK_TABLE in tree:
                fonts[name] = obj.path_id

        wanted = []
        for name in font_config.fallbacks:
            if name in fonts:
                wanted.append(fonts[name])
            else:
                result.note(f"fallback font {name!r} not in this dump — ignored")

        # Everything reachable from the chosen fallbacks, following their own
        # chains. Adding a fallback to one of these would close a loop:
        # LiberationSans -> its own Fallback -> LiberationSans.
        fallback_ids = set()
        pending = list(wanted)
        while pending:
            path_id = pending.pop()
            if path_id in fallback_ids:
                continue
            fallback_ids.add(path_id)
            tree = trees.get(path_id) or {}
            for reference in tree.get(FALLBACK_TABLE, []):
                target = reference.get("m_PathID")
                if target and target not in fallback_ids:
                    pending.append(target)

        applied = 0
        for obj in unity.objects(env, "MonoBehaviour"):
            tree = trees.get(obj.path_id)
            if tree is None:
                continue
            name = tree.get("m_Name", "")
            changed = False

            # Never make a fallback font fall back on another: that risks a cycle.
            if wanted and FALLBACK_TABLE in tree and obj.path_id not in fallback_ids:
                table = tree[FALLBACK_TABLE]
                existing = {ref.get("m_PathID") for ref in table}
                for path_id in wanted:
                    if path_id not in existing:
                        table.append(_reference(path_id))
                        changed = True
                if changed:
                    ui.detail(f"{name}: {len(table)} fallbacks")

            if (font_config.global_fallbacks and wanted
                    and name == SETTINGS_NAME and GLOBAL_FALLBACKS in tree):
                tree[GLOBAL_FALLBACKS] = [_reference(pid) for pid in wanted]
                changed = True
                ui.detail(f"{SETTINGS_NAME}: global fallbacks set")

            if font_config.neutralize_kerning and _drop_negative_kerning(tree):
                changed = True
                ui.detail(f"{name}: kerning neutralized")

            if changed:
                obj.save_typetree(tree)
                applied += 1

        if not applied:
            continue

        dest = out_root / relative
        unity.save(env, dest)

        # read back (SPEC-006/R-5)
        check = unity.load(dest)
        verified = 0
        for obj in unity.objects(check, "MonoBehaviour"):
            tree = unity.typetree(obj)
            if tree is None:
                continue
            if wanted and FALLBACK_TABLE in tree and obj.path_id not in fallback_ids:
                ids = {ref.get("m_PathID") for ref in tree[FALLBACK_TABLE]}
                if set(wanted) <= ids:
                    verified += 1
        if wanted and not verified:
            raise RuntimeError(f"{bundle.name}: font fallbacks did not stick")

        result.applied += applied
        result.files += 1
    return result
