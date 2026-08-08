"""Thin helpers over UnityPy, with the Switch texture fix always applied.

Every module that touches Unity files imports ``load`` from here instead of
calling ``UnityPy.load`` directly. That is how SPEC-009/R-6 stays true: the
swizzle fix cannot be forgotten, and forgetting it is invisible until the game is
on screen.
"""

from __future__ import annotations

from pathlib import Path

from .formats.switchtex import apply_fix

apply_fix()

import UnityPy  # noqa: E402  (must come after apply_fix)

#: Bundles keep their original compression; scene files are stored uncompressed.
PACKER_BUNDLE = "original"
PACKER_RAW = "none"


def packer_for(path) -> str:
    return PACKER_BUNDLE if str(path).endswith(".bundle") else PACKER_RAW


def load(path):
    """Open a bundle, ``.assets`` file or scene."""
    return UnityPy.load(str(path))


def save(env, dest, *, packer: str | None = None) -> int:
    """Write a modified environment out; returns the number of bytes written."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = env.file.save(packer=packer or packer_for(dest))
    dest.write_bytes(data)
    return len(data)


def typetree(obj):
    """Read an object's typetree, or ``None`` when it has no usable one."""
    try:
        return obj.read_typetree()
    except Exception:
        return None


def objects(env, *types):
    """Iterate objects, optionally filtering by type name."""
    wanted = set(types)
    for obj in env.objects:
        if wanted and obj.type.name not in wanted:
            continue
        yield obj


def textures(env):
    """Yield ``(obj, data)`` for every readable Texture2D."""
    for obj in objects(env, "Texture2D"):
        try:
            data = obj.read()
        except Exception:
            continue
        yield obj, data


def bundle_group(bundle_path) -> str:
    """``menu_assets_all_<hash>.bundle`` -> ``menu``; used to group exported PNGs."""
    name = Path(bundle_path).name
    for marker in ("_assets_all_", "_assets_"):
        if marker in name:
            return name.split(marker)[0]
    return name.split("_")[0] or "misc"
