"""Steps 4, 6 and 7: inject translated textures.

Text baked into artwork lives in three places, and all three have to be patched:

* the UI bundles under ``aa/Switch/``;
* a **second copy** inside ``sharedassets*.assets``: the battle screens use this
  one, so patching only the bundle changes nothing on screen;
* the sprite atlases, where the sprite is read from the packed atlas texture
  rather than from the loose one.

The translated image is rebuilt as *the user's own texture* + the pack's delta
(SPEC-003), so the repository never carries the artwork.
"""

from __future__ import annotations

from pathlib import Path

from .. import ui, unity
from ..config import Project
from ..formats import texdiff
from ..formats.switchtex import set_image
from ..lang import LanguagePack
from . import StepResult, bundle_rel, scene_rel, source_for


def _inject(data, delta_png) -> None:
    image = texdiff.load_translated(data.image, delta_png)
    if (image.width, image.height) != (data.m_Width, data.m_Height):
        image = image.resize((data.m_Width, data.m_Height))
    set_image(data, image)
    data.save()


def run_bundles(project: Project, pack: LanguagePack, out_root: Path, *,
                texture_index: dict | None = None) -> StepResult:
    result = StepResult("bundle-textures")
    deltas = pack.deltas()
    if not deltas:
        return result

    index = texture_index or {}
    # bundle -> {texture name: delta path}
    plan: dict[str, dict[str, Path]] = {}
    for name, delta in deltas.items():
        entry = index.get(name)
        if not entry:
            result.skipped += 1
            result.note(f"{name}: not found in this dump")
            continue
        for container in entry["containers"]:
            kind, _, filename = container.partition(":")
            if kind == "bundle":
                plan.setdefault(filename, {})[name] = delta

    progress = ui.Progress("bundles", len(plan))
    for bundle_name, wanted in sorted(plan.items()):
        relative = bundle_rel(bundle_name)
        source = source_for(project, out_root, relative)
        if not source.exists():
            progress.advance()
            continue
        env = unity.load(source)
        applied = 0
        for _, data in unity.textures(env):
            delta = wanted.get(data.m_Name)
            if delta is None:
                continue
            try:
                _inject(data, delta)
                applied += 1
            except Exception as exc:
                result.skipped += 1
                result.note(f"{data.m_Name}: {exc}")
        if applied:
            unity.save(env, out_root / relative)
            result.applied += applied
            result.files += 1
        progress.advance(bundle_name[:40])
    progress.done(f"{result.applied} textures in {result.files} bundles")
    return result


def run_scenes(project: Project, pack: LanguagePack, out_root: Path) -> StepResult:
    result = StepResult("scene-textures")
    deltas = pack.deltas()
    if not deltas:
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
        for _, data in unity.textures(env):
            delta = deltas.get(data.m_Name)
            if delta is None:
                continue
            try:
                _inject(data, delta)
                applied += 1
            except Exception as exc:
                result.skipped += 1
                result.note(f"{data.m_Name}: {exc}")
        if applied:
            unity.save(env, out_root / relative)
            result.applied += applied
            result.files += 1
            ui.detail(f"{name}: {applied} textures")
        progress.advance(name)
    progress.done(f"{result.applied} textures in {result.files} scene files")
    return result


def _render_key(value) -> tuple:
    """Normalize a sprite render-data key so it can be compared."""
    if isinstance(value, (list, tuple)) and len(value) == 2:
        guid, file_id = value
    elif isinstance(value, dict):
        guid, file_id = value.get("first"), value.get("second")
    else:
        return ()
    if isinstance(guid, dict):
        guid = tuple(sorted(guid.items()))
    return (str(guid), str(file_id))


def run_atlas(project: Project, pack: LanguagePack, out_root: Path) -> StepResult:
    """Paste translated textures into the sprite atlases that contain them."""
    result = StepResult("sprite-atlas")
    deltas = pack.deltas()
    if not deltas:
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

        sprite_keys = {}
        for obj in unity.objects(env, "Sprite"):
            tree = unity.typetree(obj)
            if tree and tree.get("m_Name") in deltas:
                sprite_keys[tree["m_Name"]] = _render_key(tree.get("m_RenderDataKey"))
        if not sprite_keys:
            progress.advance(name)
            continue

        atlas_entries = {}
        for obj in unity.objects(env, "SpriteAtlas"):
            tree = unity.typetree(obj)
            if not tree:
                continue
            for item in tree.get("m_RenderDataMap", []):
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    key, value = item
                else:
                    key, value = item.get("first"), item.get("second")
                atlas_entries[_render_key(key)] = value

        # atlas texture path_id -> [(sprite name, delta, rect, rotated)]
        plan: dict[int, list] = {}
        for sprite_name, key in sprite_keys.items():
            value = atlas_entries.get(key)
            if not value:
                continue
            texture_pid = value.get("texture", {}).get("m_PathID")
            rect = value.get("textureRect", {})
            rotated = bool((value.get("settingsRaw", 0) >> 1) & 1)
            plan.setdefault(texture_pid, []).append(
                (sprite_name, deltas[sprite_name], rect, rotated))
        if not plan:
            progress.advance(name)
            continue

        applied = 0
        for obj, data in unity.textures(env):
            if obj.path_id not in plan:
                continue
            atlas = data.image.convert("RGBA")
            for sprite_name, delta, rect, rotated in plan[obj.path_id]:
                width, height = int(rect["width"]), int(rect["height"])
                x, y = int(rect["x"]), int(rect["y"])
                top = atlas.height - (y + height)  # Unity's origin is bottom-left
                original = atlas.crop((x, top, x + width, top + height))
                if rotated:
                    original = original.rotate(-90, expand=True)
                patch = texdiff.load_translated(original, delta)
                if rotated:
                    patch = patch.rotate(90, expand=True)
                if patch.size != (width, height):
                    patch = patch.resize((width, height))
                atlas.paste(patch, (x, top))
                applied += 1
            try:
                set_image(data, atlas)
                data.save()
            except Exception as exc:
                result.skipped += 1
                result.note(f"atlas {data.m_Name}: {exc}")
                applied = 0
        if applied:
            unity.save(env, out_root / relative)
            result.applied += applied
            result.files += 1
            ui.detail(f"{name}: {applied} sprites in atlases")
        progress.advance(name)
    progress.done(f"{result.applied} sprites in {result.files} scene files")
    return result
