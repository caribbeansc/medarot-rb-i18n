"""Language-independent step: un-cramp TextMeshPro for non-Japanese text.

The game's text components are tuned for fixed-width kana::

    m_characterSpacing = -8 .. -10     pulls glyphs together
    m_charWidthMaxAdj  = 30 .. 50 %    lets TMP squeeze each glyph before
                                       shrinking the whole string

With kana (~36 px wide) that is still readable. With Latin letters (~10-18 px)
the glyphs overlap and strokes disappear: "Wild Ucorn" showed as "W'd Ucorn".
Zeroing both makes TMP shrink the text: which stays readable: instead.

This does not depend on the language, only on "not Japanese", so it runs once
into ``work/<title id>/base/`` and every language build reuses it
(SPEC-006/R-4).
"""

from __future__ import annotations

from pathlib import Path

from .. import ui, unity
from ..config import Project
from . import StepResult, bundle_rel, scene_rel

TMP_MARKER = "m_charWidthMaxAdj"

#: Bundles whose TextMeshPro typetrees are complete; the scene files have none,
#: so their objects are read using a typetree borrowed from here.
TYPETREE_DONORS = ("menu_assets_all_*.bundle", "battle_assets_all_*.bundle",
                   "tutorial_assets_all_*.bundle")


def _fix(tree) -> bool:
    changed = False
    if tree.get("m_characterSpacing", 0) < 0:
        tree["m_characterSpacing"] = 0.0
        changed = True
    if tree.get(TMP_MARKER, 0) > 0:
        tree[TMP_MARKER] = 0.0
        changed = True
    if tree.get("m_wordSpacing", 0) < 0:
        tree["m_wordSpacing"] = 0.0
        changed = True
    return changed


def _plausible(tree) -> bool:
    """Guard against mis-parsing a scene object with a borrowed typetree."""
    if not isinstance(tree.get("m_text"), str):
        return False
    if not 0 <= tree.get(TMP_MARKER, -1) <= 100:
        return False
    if not -100 <= tree.get("m_characterSpacing", 999) <= 100:
        return False
    return 0 < tree.get("m_fontSize", 0) <= 500


def run_bundles(project: Project, out_root: Path) -> StepResult:
    result = StepResult("metrics-bundles")
    bundles = project.bundles()
    progress = ui.Progress("bundles", len(bundles), every=25)
    for bundle in bundles:
        relative = bundle_rel(bundle.name)
        source = out_root / relative
        if not source.exists():
            source = bundle
        try:
            env = unity.load(source)
        except Exception:
            progress.advance()
            continue
        applied = 0
        for obj in unity.objects(env, "MonoBehaviour"):
            tree = unity.typetree(obj)
            if tree is None or TMP_MARKER not in tree:
                continue
            if _fix(tree):
                obj.save_typetree(tree)
                applied += 1
        if applied:
            unity.save(env, out_root / relative)
            result.applied += applied
            result.files += 1
        progress.advance(bundle.name[:40])
    progress.done(f"{result.applied} components in {result.files} bundles")
    return result


def _donor_typetrees(project: Project) -> dict:
    trees = {}
    for pattern in TYPETREE_DONORS:
        for bundle in project.bundles_dir.glob(pattern):
            try:
                env = unity.load(bundle)
            except Exception:
                continue
            for obj in unity.objects(env, "MonoBehaviour"):
                tree = unity.typetree(obj)
                if tree is None or TMP_MARKER not in tree:
                    continue
                serialized = obj.serialized_type
                trees.setdefault(serialized.m_ClassName or "?", serialized.nodes)
    return trees


def run_scenes(project: Project, out_root: Path) -> StepResult:
    result = StepResult("metrics-scenes")
    donors = _donor_typetrees(project)
    if not donors:
        result.note("no TextMeshPro typetree found in the bundles")
        return result

    scenes = project.scenes()
    for index, scene in enumerate(scenes, start=1):
        relative = scene_rel(scene.name)
        source = out_root / relative
        if not source.exists():
            source = scene
        try:
            env = unity.load(source)
        except Exception:
            continue

        # One scene can hold tens of thousands of objects, each of which is parsed
        # against every borrowed typetree. That is minutes of work with nothing to
        # show, so the progress counts objects, not files.
        candidates = list(unity.objects(env, "MonoBehaviour"))
        progress = ui.Progress(f"[{index}/{len(scenes)}] {scene.name}",
                               len(candidates), every=500)
        applied = 0
        for obj in candidates:
            for nodes in donors.values():
                try:
                    tree = obj.read_typetree(nodes)
                except Exception:
                    continue
                if not _plausible(tree):
                    continue
                if _fix(tree):
                    obj.save_typetree(tree, nodes)
                    applied += 1
                break
            progress.advance()
        progress.done()
        if applied:
            unity.save(env, out_root / relative)
            result.applied += applied
            result.files += 1
            ui.detail(f"{scene.name}: {applied} components of {len(candidates)}")
    ui.detail(f"{result.applied} components in {result.files} scene files")
    return result


def prepare(project: Project) -> list[StepResult]:
    """Build the language-independent cache for this dump."""
    out_root = project.base_cache
    out_root.mkdir(parents=True, exist_ok=True)
    project.record_dump()
    ui.step("Fixing text metrics in bundles (the slow part)")
    bundles = run_bundles(project, out_root)
    ui.step("Fixing text metrics in scenes")
    scenes = run_scenes(project, out_root)
    return [bundles, scenes]
