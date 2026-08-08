"""Copy a built mod into the emulators installed on this machine.

Detection covers the Ryujinx-style ``mods/contents/<lowercase title id>/`` layout
and the yuzu-style ``load/<UPPERCASE TITLE ID>/`` one, on Windows, macOS and
Linux (SPEC-006/R-9). Nothing outside ``<mods dir>/<mod name>/`` is ever touched.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import TITLE_ID, ModTarget, Project, detect_mod_targets
from .lang import LanguagePack


class InstallError(Exception):
    pass


@dataclass
class Installed:
    emulator: str
    path: Path
    files: int


def built_mod(project: Project, pack: LanguagePack) -> Path:
    mod = project.build_lang(pack.code) / pack.mod_name
    if not (mod / "romfs").is_dir():
        raise InstallError(
            f"nothing built for {pack.code} yet — run:  mrb build {pack.code}")
    return mod


def targets(explicit=None, title_id: str | None = None) -> list[ModTarget]:
    """Where to install: an explicit directory, or whatever was detected."""
    if explicit:
        path = Path(explicit).expanduser()
        return [ModTarget(emulator="custom", path=path, style="custom")]
    return detect_mod_targets(title_id or TITLE_ID)


def plan(project: Project, pack: LanguagePack, explicit=None) -> list[tuple[ModTarget, Path]]:
    """``[(target, final mod directory)]`` — what an install would write."""
    return [(target, target.path / pack.mod_name)
            for target in targets(explicit, project.title_id)]


def install(project: Project, pack: LanguagePack, explicit=None) -> list[Installed]:
    source = built_mod(project, pack)
    done = []
    for target, destination in plan(project, pack, explicit):
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination)
        files = sum(1 for p in destination.rglob("*") if p.is_file())
        done.append(Installed(emulator=target.emulator, path=destination, files=files))
    if not done:
        raise InstallError(
            "no emulator found. Pass the directory yourself, e.g.\n"
            "  mrb install <lang> --to "
            "'~/Library/Application Support/Ryujinx/mods/contents/0100cb6024ff8000'")
    return done


def uninstall(project: Project, pack: LanguagePack, explicit=None) -> list[Path]:
    removed = []
    for _, destination in plan(project, pack, explicit):
        if destination.exists():
            shutil.rmtree(destination)
            removed.append(destination)
    return removed
