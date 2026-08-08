"""Project paths, user configuration and emulator detection.

Nothing here touches the game: it only decides *where* things are. The user's
romfs is never copied into the project; every step reads it in place.
"""

from __future__ import annotations

import json
import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

#: Base game title id of the Kuwagata version. The update (…8800) is applied on
#: top of it by the emulator, so mods always go under the base id.
#:
#: The sister release (Kabuto Ver.) is a different title with a different id. The
#: file formats are identical, so the tools work on it, but the mod has to be
#: installed under *its* id: hence `mrb setup --title-id`.
TITLE_ID = "0100CB6024FF8000"

CONFIG_NAME = "mrb.config.json"

#: The two retail releases.
RELEASES = {
    "0100CB6024FF8000": {"name": "Kuwagata Ver."},
    "0100DE4023982000": {"name": "Kabuto Ver."},
}

#: Unity writes a ``build-guid`` into ``Data/boot.config``, one per build. It is
#: the only thing that tells the four known dumps apart: without the update, the
#: two releases ship a byte-identical romfs except for four files, and none of the
#: usual markers (file names, sizes, table contents) differ at all.
BUILD_GUIDS = {
    "5f910fe43b4b45758b7b1e36af48fea4": ("0100CB6024FF8000", "Kuwagata Ver., update v1.1"),
    "9a229dcba8c1484eaf260e0f76dd1938": ("0100CB6024FF8000", "Kuwagata Ver., base game"),
    "d36acbaafb9f472a9c94dbe0bc4d6d96": ("0100DE4023982000", "Kabuto Ver., update v1.1"),
    "44c30c35db8f47518de97e8d199abae8": ("0100DE4023982000", "Kabuto Ver., base game"),
}

BOOT_CONFIG = "Data/boot.config"

#: Relative to the romfs root.
IDXRES_DIR = "Data/StreamingAssets/IdxResData"
BUNDLE_DIR = "Data/StreamingAssets/aa/Switch"
DATA_DIR = "Data"

#: Scene containers that hold text or textures. Order is stable so builds are
#: reproducible.
SCENE_FILES = [
    "level0", "level1", "level2", "level3", "level4",
    "sharedassets0.assets", "sharedassets1.assets", "sharedassets2.assets",
    "sharedassets3.assets", "sharedassets4.assets",
    "resources.assets", "globalgamemanagers.assets",
]

FONT_BUNDLE_GLOB = "font_assets_all_*.bundle"


class ConfigError(Exception):
    """Raised when the project cannot be located or the romfs is unusable."""


def repo_root() -> Path:
    """The checkout this module lives in."""
    return Path(__file__).resolve().parent.parent


def _candidate_romfs(root: Path) -> list[Path]:
    """Places a romfs plausibly sits, in priority order."""
    env = os.environ.get("MEDAROT_ROMFS")
    out = [Path(env).expanduser()] if env else []
    out += [
        root / "game" / "romfs",
        root / "romfs",
        root.parent / "base" / "romfs",
    ]
    return out


def build_guid(romfs) -> str | None:
    """The Unity build id of a dump, from ``Data/boot.config``."""
    path = Path(romfs) / BOOT_CONFIG
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        if line.startswith("build-guid="):
            return line.split("=", 1)[1].strip()
    return None


def detect_release(romfs) -> tuple[str, str] | None:
    """``(title id, release name)`` for a romfs, or ``None`` if unrecognised.

    Saves the user from having to know their own title id, and stops a mod being
    installed under the wrong game.
    """
    guid = build_guid(romfs)
    if guid and guid in BUILD_GUIDS:
        return BUILD_GUIDS[guid]
    return None


def release_name(title_id: str) -> str:
    return RELEASES.get(title_id.upper(), {}).get("name", "unknown release")


def looks_like_romfs(path) -> bool:
    """True if ``path`` is an extracted romfs of this game."""
    if not path:
        return False
    path = Path(path)
    tables = path / IDXRES_DIR
    if not tables.is_dir():
        return False
    return any(tables.glob("IdxRes_*.bytes"))


@dataclass
class Project:
    root: Path
    romfs: Path | None
    work: Path
    build: Path
    langs: Path
    #: Whether build steps may read from the prepared cache. A language that does
    #: not want the metric fixes (``font.fix_tmp_metrics: false``) turns this off.
    use_base_cache: bool = True
    #: Which title the mod is installed under. Change it for the Kabuto version.
    title_id: str = TITLE_ID

    # ---------------------------------------------------------------- paths --
    @property
    def config_file(self) -> Path:
        return self.root / CONFIG_NAME

    @property
    def tables_dir(self) -> Path:
        return self.require_romfs() / IDXRES_DIR

    @property
    def bundles_dir(self) -> Path:
        return self.require_romfs() / BUNDLE_DIR

    @property
    def data_dir(self) -> Path:
        return self.require_romfs() / DATA_DIR

    @property
    def dump_work(self) -> Path:
        """Working area for *this* dump.

        Keyed by title id, because the game has a sister release: the two dumps
        share file names but not contents, and mixing their inventories or their
        caches would produce a mod built from the wrong game.
        """
        return self.work / self.title_id.lower()

    @property
    def raw_dir(self) -> Path:
        return self.dump_work / "raw"

    @property
    def inventory_dir(self) -> Path:
        return self.dump_work / "inventory"

    @property
    def assets_dir(self) -> Path:
        return self.dump_work / "assets"

    @property
    def base_cache(self) -> Path:
        """Language-independent patched files produced by ``mrb prepare``."""
        return self.dump_work / "base"

    def work_lang(self, code: str) -> Path:
        return self.dump_work / "lang" / code

    def build_lang(self, code: str) -> Path:
        return self.build / code

    def lang_dir(self, code: str) -> Path:
        return self.langs / code

    # ------------------------------------------------------------- romfs ----
    def has_romfs(self) -> bool:
        return looks_like_romfs(self.romfs)

    def require_romfs(self) -> Path:
        if not self.has_romfs():
            raise ConfigError(
                "No game files configured. Extract the romfs of your own dump and "
                "run:  python mrb.py setup --romfs /path/to/romfs"
            )
        return Path(self.romfs)

    def bundles(self) -> list[Path]:
        return sorted(self.bundles_dir.glob("*.bundle"))

    def scenes(self) -> list[Path]:
        return [self.data_dir / name for name in SCENE_FILES
                if (self.data_dir / name).exists()]

    def font_bundles(self) -> list[Path]:
        return sorted(self.bundles_dir.glob(FONT_BUNDLE_GLOB))

    def base_or_romfs(self, relative: str) -> Path:
        """Prefer the prepared cache over the pristine romfs for ``relative``."""
        cached = self.base_cache / relative
        if cached.exists():
            return cached
        return self.require_romfs() / relative

    # -------------------------------------------------------------- dumps ---
    def dump_fingerprint(self) -> str:
        """A cheap fingerprint of the romfs: names and sizes, no reading.

        The base game and the v1.1 update share a title id but not their files,
        so the title id alone cannot tell you which one produced a cache.
        """
        import hashlib

        romfs = self.require_romfs()
        guid = build_guid(romfs)
        if guid:
            return guid[:16]

        digest = hashlib.sha256()
        for pattern in (f"{IDXRES_DIR}/*.bytes", f"{BUNDLE_DIR}/*.bundle"):
            for path in sorted(romfs.glob(pattern)):
                digest.update(path.name.encode("utf-8"))
                digest.update(str(path.stat().st_size).encode("ascii"))
        return digest.hexdigest()[:16]

    @property
    def dump_stamp_file(self) -> Path:
        return self.dump_work / "dump.json"

    def record_dump(self) -> None:
        stamp = {"title_id": self.title_id, "romfs": str(self.romfs),
                 "fingerprint": self.dump_fingerprint()}
        self.dump_stamp_file.parent.mkdir(parents=True, exist_ok=True)
        self.dump_stamp_file.write_text(json.dumps(stamp, indent=2) + "\n",
                                        encoding="utf-8")

    def dump_changed(self) -> bool:
        """True if the working area was built from a different dump."""
        if not self.dump_stamp_file.exists():
            return False
        try:
            stored = json.loads(self.dump_stamp_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return stored.get("fingerprint") not in (None, self.dump_fingerprint())

    # ------------------------------------------------------------- config ---
    def save(self) -> None:
        data = {"romfs": str(self.romfs) if self.romfs else None,
                "title_id": self.title_id}
        self.config_file.write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def set_title_id(self, title_id: str) -> None:
        cleaned = str(title_id).strip().upper()
        if len(cleaned) != 16 or any(c not in "0123456789ABCDEF" for c in cleaned):
            raise ConfigError(
                f"{title_id!r} is not a title id: expected 16 hex digits, "
                f"e.g. {TITLE_ID}")
        self.title_id = cleaned
        self.save()

    def set_romfs(self, path, *, detect: bool = True) -> str | None:
        """Point the project at a romfs. Returns the release name if recognised."""
        path = Path(path).expanduser().resolve()
        if not looks_like_romfs(path):
            raise ConfigError(
                f"{path} does not look like this game's romfs: expected "
                f"{IDXRES_DIR}/IdxRes_*.bytes underneath it."
            )
        self.romfs = path
        found = detect_release(path) if detect else None
        if found:
            self.title_id = found[0]
        self.save()
        return found[1] if found else None


def load(root: Path | None = None) -> Project:
    """Load the project, picking up a configured or auto-detected romfs.

    Precedence: ``MEDAROT_ROMFS`` / ``MEDAROT_TITLE_ID``, then the stored config,
    then the usual places. The environment wins so that a second dump: the
    Kabuto release, say: can be worked on without disturbing the saved setup.
    """
    root = Path(root) if root else repo_root()
    romfs = None

    env_romfs = os.environ.get("MEDAROT_ROMFS")
    if env_romfs and looks_like_romfs(Path(env_romfs).expanduser()):
        romfs = Path(env_romfs).expanduser().resolve()

    title_id = os.environ.get("MEDAROT_TITLE_ID", "").strip().upper() or TITLE_ID
    config_file = root / CONFIG_NAME
    if config_file.exists():
        try:
            stored_config = json.loads(config_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            stored_config = {}
        stored = stored_config.get("romfs")
        if romfs is None and stored and looks_like_romfs(stored):
            romfs = Path(stored)
        if not os.environ.get("MEDAROT_TITLE_ID"):
            title_id = stored_config.get("title_id") or TITLE_ID

    if romfs is None:
        for candidate in _candidate_romfs(root):
            if looks_like_romfs(candidate):
                romfs = candidate.resolve()
                break

    return Project(
        root=root,
        romfs=romfs,
        work=root / "work",
        build=root / "build",
        langs=root / "langs",
        title_id=title_id,
    )


# ------------------------------------------------------------- emulators ----

@dataclass
class ModTarget:
    """A directory where an emulator looks for mods."""
    emulator: str
    path: Path        # <…>/<title id>/ : the mod goes in a subdirectory of this
    style: str        # "ryujinx" | "yuzu"


def _appdata() -> Path | None:
    value = os.environ.get("APPDATA")
    return Path(value) if value else None


def _emulator_roots() -> list[tuple[str, Path, str]]:
    """``(emulator, directory holding per-title mod dirs, style)`` candidates."""
    system = platform.system()
    home = Path.home()
    out: list[tuple[str, Path, str]] = []

    # Ryujinx and its forks: <data>/mods/contents/<lowercase title id>/<Mod>/romfs
    ryujinx_names = ["Ryujinx", "Ryubing"]
    # yuzu-family: <data>/load/<UPPERCASE TITLE ID>/<Mod>/romfs
    yuzu_names = ["yuzu", "sudachi", "eden", "citron", "suyu"]

    if system == "Windows":
        appdata = _appdata()
        if appdata:
            for name in ryujinx_names:
                out.append((name, appdata / name / "mods" / "contents", "ryujinx"))
            for name in yuzu_names:
                out.append((name, appdata / name / "load", "yuzu"))
    elif system == "Darwin":
        support = home / "Library" / "Application Support"
        for name in ryujinx_names:
            out.append((name, support / name / "mods" / "contents", "ryujinx"))
        # Astris ships Ryujinx inside an app container.
        out.append((
            "Astris",
            home / "Library" / "Containers" / "V380-Ori.Astris" / "Data" / "Library"
            / "Application Support" / "Ryujinx" / "mods" / "contents",
            "ryujinx",
        ))
        for name in yuzu_names:
            out.append((name, support / name / "load", "yuzu"))
    else:  # Linux and the rest
        config = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
        share = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
        for name in ryujinx_names:
            out.append((name, config / name / "mods" / "contents", "ryujinx"))
            out.append((name, share / name / "mods" / "contents", "ryujinx"))
        for name in yuzu_names:
            out.append((name, share / name / "load", "yuzu"))
            out.append((name, config / name / "load", "yuzu"))
        # Flatpak installs
        flatpak = home / ".var" / "app"
        out.append(("Ryujinx (flatpak)",
                    flatpak / "org.ryujinx.Ryujinx" / "config" / "Ryujinx" / "mods"
                    / "contents", "ryujinx"))

    return out


def detect_mod_targets(title_id: str = TITLE_ID) -> list[ModTarget]:
    """Emulator mod directories that exist on this machine (SPEC-006/R-9)."""
    found: list[ModTarget] = []
    seen: set[Path] = set()
    for emulator, root, style in _emulator_roots():
        if not root.exists():
            continue
        title = title_id.lower() if style == "ryujinx" else title_id.upper()
        target = root / title
        if target in seen:
            continue
        seen.add(target)
        found.append(ModTarget(emulator=emulator, path=target, style=style))
    return found


def python_hint() -> str:
    """How the user should invoke Python, for messages."""
    return "py" if platform.system() == "Windows" else "python3"


def interpreter() -> str:
    return sys.executable or python_hint()
