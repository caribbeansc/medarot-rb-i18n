"""Translate text that is baked into artwork.

This toolkit deliberately does **not** draw text for you: image editing belongs in
an image editor. What it does is the part that is specific to this game:

1. ``mrb assets`` exports a texture out of your own dump as a PNG — decoded
   correctly, including the 30 textures that the UnityPy swizzle bug corrupts;
2. you edit that PNG however you like (Photoshop, GIMP, Krita, Aseprite…);
3. ``mrb textures <lang> --import edited.png`` diffs it against the original and
   stores only what you changed, as an overlay plus a mask (SPEC-003);
4. ``mrb build`` rebuilds the final texture as *your* original plus that delta and
   injects it into the bundles, the scenes and the sprite atlases.

Step 3 is what keeps the repository free of the game's artwork, and step 4 is what
makes a translated texture actually show up on screen.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from . import extract
from .config import ConfigError, Project
from .formats import texdiff
from .lang import LanguagePack

#: Optional, human-facing index of what each translated texture says.
INDEX_NAME = "textures.json"


class TextureError(Exception):
    pass


@dataclass
class DeltaResult:
    name: str
    delta: Path
    mask: Path
    percent: float
    #: Sides of the texture the edit runs into. Text that reaches the edge is
    #: almost always text that got clipped on screen: a translation is usually
    #: wider than the Japanese it replaces, and nothing warns you at build time.
    touches: tuple = ()

    def fits(self) -> bool:
        return not self.touches


def original_image(project: Project, name: str) -> Image.Image:
    """The untranslated texture, from the export cache or straight from the dump."""
    for candidate in sorted(project.assets_dir.rglob(f"{name}.png")):
        return Image.open(candidate).convert("RGBA")
    try:
        image = extract.find_texture(project, name)
    except ConfigError as exc:
        raise TextureError(
            f"texture {name!r} is not in work/assets and the game files are not "
            f"configured, so it cannot be looked up ({exc}). Configure them with "
            f"'mrb setup', then 'mrb assets --list'") from exc
    if image is None:
        raise TextureError(
            f"texture {name!r} not found in your dump — check the name with "
            f"'mrb assets --list --filter {name[:8]}'")
    return image


def import_edited(project: Project, pack: LanguagePack, png_path,
                  name: str | None = None) -> DeltaResult:
    """Turn an edited PNG into a delta against the user's own texture."""
    png_path = Path(png_path)
    if not png_path.exists():
        raise TextureError(f"{png_path}: not found")
    name = name or png_path.stem
    original = original_image(project, name)
    edited = Image.open(png_path).convert("RGBA")
    if edited.size != original.size:
        edited = edited.resize(original.size)
    overlay, mask, percent = texdiff.make_diff(original, edited)
    if percent == 0.0:
        raise TextureError(
            f"{name}: the image is identical to the original — nothing to store")
    delta = pack.delta_dir / f"{name}.png"
    texdiff.save_diff(delta, overlay, mask)
    return DeltaResult(name=name, delta=delta, mask=texdiff.mask_path(delta),
                       percent=percent, touches=edge_contact(original, edited, mask))


def edge_contact(original: Image.Image, edited: Image.Image,
                 mask: Image.Image) -> tuple:
    """Which edges the edit reaches that the original did not.

    A translation is usually wider than the Japanese it replaces, and the game
    clips it silently: the giveaway is an edit that runs into an edge where the
    original texture had nothing. Comparing against the original matters — plenty
    of textures legitimately paint all the way to the border, and flagging those
    would bury the real cases in noise.
    """
    box = mask.getbbox()
    if box is None:
        return ()
    left, top, right, bottom = box
    original_box = original.convert("RGBA").split()[3].getbbox() or (0, 0, 0, 0)
    touched = []
    if left == 0 and original_box[0] > 0:
        touched.append("left")
    if top == 0 and original_box[1] > 0:
        touched.append("top")
    if right >= edited.width and original_box[2] < original.width:
        touched.append("right")
    if bottom >= edited.height and original_box[3] < original.height:
        touched.append("bottom")
    return tuple(touched)


def preview(project: Project, pack: LanguagePack, name: str, dest=None) -> Path:
    """Write out the final translated texture, to check it before building."""
    delta = pack.deltas().get(name)
    if delta is None:
        raise TextureError(f"{name}: {pack.code} has no delta for that texture")
    image = texdiff.load_translated(original_image(project, name), delta)
    target = Path(dest or (project.work / "preview" / f"{name}.png"))
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    return target


def index_path(pack: LanguagePack) -> Path:
    return pack.textures_dir / INDEX_NAME


def load_index(pack: LanguagePack) -> dict:
    """``{texture name: {"text": ..., "note": ...}}`` — documentation only."""
    path = index_path(pack)
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {item["texture"]: item for item in doc.get("textures", [])}


def save_index(pack: LanguagePack, items: list[dict]) -> Path:
    path = index_path(pack)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"textures": items}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    return path


def status(project: Project, pack: LanguagePack) -> list[dict]:
    """One row per texture this pack knows about: does it have a delta, where does
    it live in the game, and what is it supposed to say."""
    deltas = pack.deltas()
    index = load_index(pack)
    names = sorted(set(deltas) | set(index))
    known = {}
    if project.has_romfs():
        cache = project.inventory_dir / "textures.json"
        if cache.exists():
            known = json.loads(cache.read_text(encoding="utf-8"))
    rows = []
    for name in names:
        entry = known.get(name, {})
        rows.append({
            "texture": name,
            "delta": bool(deltas.get(name)),
            "text": index.get(name, {}).get("text", ""),
            "size": f"{entry.get('width', '?')}x{entry.get('height', '?')}",
            "format": entry.get("format", "?"),
            "copies": len(entry.get("containers", [])),
        })
    return rows
