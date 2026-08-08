"""Package a built mod for the two layouts Switch modding actually uses.

Both are LayeredFS; they differ only in where the files go and whether a mod has
a name:

*emulator* — Ryujinx-family and yuzu-family read a **named** mod directory::

    <mods dir>/<title id>/MedarotRB_ES/romfs/Data/…

*atmosphere* — real hardware (Atmosphère CFW) reads one romfs tree per title,
with no room for a mod name, straight off the SD card::

    sdmc:/atmosphere/contents/0100CB6024FF8000/romfs/Data/…

See ``docs/specs/SPEC-006-build-pipeline.md`` (R-11 … R-14).
"""

from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .config import TITLE_ID, Project
from .lang import LanguagePack

EMULATOR = "emulator"
ATMOSPHERE = "atmosphere"
FORMATS = (EMULATOR, ATMOSPHERE)

#: Atmosphère's own path convention: uppercase title id, under /atmosphere.
ATMOSPHERE_ROOT = "atmosphere/contents"


class PackageError(Exception):
    pass


@dataclass
class Package:
    format: str
    root: Path          # what to copy (or zip) as-is
    romfs: Path         # the romfs inside it
    files: int
    archive: Path | None = None

    def where(self) -> str:
        if self.format == ATMOSPHERE:
            return "copy the 'atmosphere' folder to the root of your SD card"
        return "copy the mod folder into your emulator's mods directory"


def source_romfs(project: Project, pack: LanguagePack) -> Path:
    romfs = project.build_lang(pack.code) / pack.mod_name / "romfs"
    if not romfs.is_dir():
        raise PackageError(
            f"nothing built for {pack.code} yet — run:  mrb build {pack.code}")
    return romfs


def relative_root(pack: LanguagePack, fmt: str, title_id: str = TITLE_ID) -> Path:
    """Where the romfs sits inside the packaged tree."""
    if fmt == ATMOSPHERE:
        return Path(ATMOSPHERE_ROOT) / title_id.upper() / "romfs"
    if fmt == EMULATOR:
        return Path(pack.mod_name) / "romfs"
    raise PackageError(f"unknown format {fmt!r} (expected one of {', '.join(FORMATS)})")


def stage(project: Project, pack: LanguagePack, fmt: str, out_dir=None) -> Package:
    """Lay the built mod out in the requested format under ``dist/``."""
    romfs = source_romfs(project, pack)
    base = Path(out_dir) if out_dir else project.root / "dist" / pack.code / fmt
    if base.exists():
        shutil.rmtree(base)

    target = base / relative_root(pack, fmt, project.title_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(romfs, target)

    files = sum(1 for p in target.rglob("*") if p.is_file())
    return Package(format=fmt, root=base, romfs=target, files=files)


def archive(package: Package, dest=None) -> Path:
    """Zip a staged package, ready to unpack where it belongs."""
    target = Path(dest) if dest else package.root.with_suffix(".zip")
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(package.root.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(package.root))
    package.archive = target
    return target


def build_all(project: Project, pack: LanguagePack, formats=FORMATS,
              *, make_archive: bool = False) -> list[Package]:
    packages = []
    for fmt in formats:
        package = stage(project, pack, fmt)
        if make_archive:
            archive(package)
        packages.append(package)
    return packages


def install_to_sd(project: Project, pack: LanguagePack, sd_root) -> Package:
    """Write the Atmosphère layout straight onto a mounted SD card.

    Only ``atmosphere/contents/<title id>/romfs`` is touched; anything else on the
    card is left alone (SPEC-006/R-14).
    """
    sd_root = Path(sd_root).expanduser()
    if not sd_root.is_dir():
        raise PackageError(f"{sd_root}: not a directory — is the SD card mounted?")
    romfs = source_romfs(project, pack)

    target = sd_root / relative_root(pack, ATMOSPHERE, project.title_id)
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(romfs, target)
    files = sum(1 for p in target.rglob("*") if p.is_file())
    return Package(format=ATMOSPHERE, root=sd_root, romfs=target, files=files)
