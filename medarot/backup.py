"""Turn a Switch game backup into an extracted romfs the rest of the tool reads.

The pipeline everywhere else works on an already-decrypted romfs and needs no
keys at all. This module is the one exception: it takes a backup the player
dumped from their own cartridge or eShop copy — ``.xci``, ``.nsp``, or the
compressed ``.xcz`` / ``.nsz`` — decrypts it with the player's own keys, and
writes out ``Data/StreamingAssets/…`` so ``setup`` can point at it.

Nothing here ships game data or keys. It drives ``hactool`` (bundled per
platform, ISC-licensed) and, for compressed dumps, the ``nsz`` decompressor.
The player supplies ``prod.keys`` (always) and ``title.keys`` (only if an
update carries title-key crypto and the ticket is missing).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import ui

XCI_SUFFIXES = {".xci"}
NSP_SUFFIXES = {".nsp"}
COMPRESSED = {".xcz": ".xci", ".nsz": ".nsp"}
BACKUP_SUFFIXES = XCI_SUFFIXES | NSP_SUFFIXES | set(COMPRESSED)

#: Where players keep prod.keys/title.keys, in priority order.
KEY_DIRS = [
    Path.home() / ".switch",
    Path.home() / "AppData" / "Roaming" / "Ryujinx" / "system",  # Windows
    Path.home() / "Library" / "Application Support" / "Ryujinx" / "system",  # macOS
    Path.home() / ".config" / "Ryujinx" / "system",  # Linux
    Path.home() / ".local" / "share" / "Citron" / "keys",
]


class BackupError(Exception):
    """The backup could not be turned into a romfs."""


@dataclass
class Keys:
    prod: Path
    title: Path | None = None

    @classmethod
    def find(cls, near: Path | None = None) -> "Keys | None":
        """Locate prod.keys (and title.keys) automatically, or return None."""
        dirs: list[Path] = []
        if near is not None:
            dirs.append(Path(near) if near.is_dir() else near.parent)
        env = os.environ.get("MEDAROT_KEYS")
        if env:
            dirs.append(Path(env) if Path(env).is_dir() else Path(env).parent)
        dirs += KEY_DIRS
        for directory in dirs:
            prod = directory / "prod.keys"
            if prod.is_file():
                title = directory / "title.keys"
                return cls(prod, title if title.is_file() else None)
        return None


@dataclass
class Tools:
    hactool: Path
    nsz: Path | None = None

    @classmethod
    def locate(cls) -> "Tools":
        """Find the bundled hactool (and optional nsz), or raise."""
        for base in _tool_dirs():
            exe = base / _exe("hactool")
            if exe.is_file():
                nsz = base / _exe("nsz")
                return cls(exe, nsz if nsz.is_file() else _which("nsz"))
        found = _which("hactool")
        if found:
            return cls(found, _which("nsz"))
        raise BackupError(
            "hactool was not found. The packaged app ships it; from a source "
            "checkout, put a hactool binary on PATH or in tools/bin/.")


@dataclass
class Extraction:
    romfs: Path
    release: str | None = None
    build_guid: str | None = None
    used_update: bool = False
    warnings: list[str] = field(default_factory=list)


def _tool_dirs() -> list[Path]:
    here = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return [here / "tools" / "bin", here / "tools", here]


def _exe(name: str) -> str:
    return name + (".exe" if os.name == "nt" else "")


def _which(name: str) -> Path | None:
    found = shutil.which(name) or shutil.which(_exe(name))
    return Path(found) if found else None


def is_backup(path) -> bool:
    return Path(path).suffix.lower() in BACKUP_SUFFIXES


def _run(tool: Tools, args: list[str], keys: Keys, *, log: Path) -> None:
    cmd = [str(tool.hactool), "-k", str(keys.prod)] + args
    with log.open("a", encoding="utf-8") as handle:
        handle.write("$ " + " ".join(cmd) + "\n")
        proc = subprocess.run(cmd, stdout=handle, stderr=subprocess.STDOUT,
                              text=True)
    if proc.returncode != 0:
        raise BackupError(
            f"hactool failed ({proc.returncode}). See {log} for details. "
            "The usual cause is missing or wrong prod.keys.")


def _content_types(tool: Tools, ncas: list[Path], keys: Keys, *,
                   log: Path) -> dict[Path, dict[str, str]]:
    """Map each NCA to its {type, rights_id} by inspecting hactool's output."""
    out = {}
    for nca in ncas:
        cmd = [str(tool.hactool), "-k", str(keys.prod), "-t", "nca", str(nca)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        info = {"type": "", "rights_id": ""}
        for line in proc.stdout.splitlines():
            low = line.lower()
            if "content type:" in low:
                info["type"] = line.split(":", 1)[1].strip()
            elif "rights id:" in low:
                info["rights_id"] = line.split(":", 1)[1].strip()
        out[nca] = info
    return out


def _titlekey_from_ticket(ticket: Path) -> str | None:
    """The 16-byte title key lives at offset 0x180 in a .tik."""
    try:
        data = ticket.read_bytes()
    except OSError:
        return None
    if len(data) < 0x190:
        return None
    return data[0x180:0x190].hex()


def _titlekey_from_file(title_keys: Path | None, rights_id: str) -> str | None:
    """Look up ``rights_id = titlekey`` in a title.keys file."""
    if title_keys is None or not rights_id:
        return None
    try:
        text = title_keys.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    want = rights_id.lower()
    for line in text.splitlines():
        if "=" not in line:
            continue
        left, right = line.split("=", 1)
        if left.strip().lower() == want:
            return right.strip()
    return None


def _program_nca(types: dict[Path, dict[str, str]]) -> Path | None:
    for nca, info in types.items():
        if info["type"].lower() == "program":
            return nca
    return None


def _extract_container(tool: Tools, backup: Path, out: Path, keys: Keys, *,
                       log: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    suffix = backup.suffix.lower()
    if suffix in XCI_SUFFIXES:
        _run(tool, ["-t", "xci", "--securedir", str(out), str(backup)],
             keys, log=log)
    else:
        _run(tool, ["-t", "pfs0", "--pfs0dir", str(out), str(backup)],
             keys, log=log)


def _run_nsz_in_process(argv: list[str]) -> bool:
    """Drive the bundled nsz module by faking its argv. Returns success.

    In the packaged app there is no standalone ``nsz`` executable to spawn, but
    the module is bundled (``--collect-all nsz``), so we call its entry point
    directly. nsz keys come from the same prod.keys the app already located.
    """
    try:
        import nsz.__main__ as nsz_main
    except Exception:
        return False
    old = sys.argv
    sys.argv = ["nsz"] + argv
    try:
        nsz_main.main()
        return True
    except SystemExit as exc:
        return not exc.code
    except Exception:
        return False
    finally:
        sys.argv = old


def _decompress(tool: Tools, backup: Path, work: Path) -> Path:
    """Turn an .xcz/.nsz into its .xci/.nsp with the nsz tool."""
    target_suffix = COMPRESSED[backup.suffix.lower()]
    out_dir = work / "decompressed"
    out_dir.mkdir(parents=True, exist_ok=True)
    ui.info(f"Decompressing {backup.name} (this can take a while)…")
    args = ["-D", "-o", str(out_dir), str(backup)]

    ok = False
    if tool.nsz is not None:  # a standalone nsz on PATH (source checkouts)
        proc = subprocess.run([str(tool.nsz), *args], capture_output=True, text=True)
        ok = proc.returncode == 0
        if not ok and "No module" not in proc.stderr:
            ui.warn(proc.stderr[:300])
    if not ok:  # the bundled module (packaged app)
        ok = _run_nsz_in_process(args)
    if not ok:
        raise BackupError(
            f"{backup.name} is a compressed dump and it could not be "
            "decompressed. From a source checkout run 'pip install nsz', or "
            f"decompress it to {target_suffix} yourself first.")
    for candidate in out_dir.glob(f"*{target_suffix}"):
        return candidate
    raise BackupError(f"decompression produced no {target_suffix} file")


def extract(backup, out_dir, *, keys: Keys, update=None,
            tools: Tools | None = None, work_dir=None) -> Extraction:
    """Decrypt ``backup`` into an extracted romfs under ``out_dir``.

    ``update`` is an optional second backup (an update .nsp) to layer on top of
    the base. When the base backup already contains the program, ``update`` is
    not needed.
    """
    from . import config

    tools = tools or Tools.locate()
    backup = Path(backup)
    out_dir = Path(out_dir)
    work = Path(work_dir) if work_dir else out_dir.parent / "_backup_work"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    log = work / "hactool.log"
    result = Extraction(romfs=out_dir)

    if backup.suffix.lower() in COMPRESSED:
        backup = _decompress(tools, backup, work)
    if update is not None and Path(update).suffix.lower() in COMPRESSED:
        update = _decompress(tools, Path(update), work)

    ui.step(f"Reading {backup.name}")
    base_dir = work / "base"
    _extract_container(tools, backup, base_dir, keys, log=log)
    base_ncas = sorted(p for p in base_dir.glob("*.nca")
                       if not p.name.endswith(".cnmt.nca"))
    if not base_ncas:
        raise BackupError(f"no NCAs inside {backup.name}: not a game backup, "
                          "or the keys are wrong.")
    base_types = _content_types(tools, base_ncas, keys, log=log)
    base_program = _program_nca(base_types)
    if base_program is None:
        raise BackupError(f"{backup.name} has no Program content — is it a DLC "
                          "or add-on rather than the game?")

    update_program = None
    titlekey = None
    if update is not None:
        ui.step(f"Reading {Path(update).name}")
        upd_dir = work / "update"
        _extract_container(tools, Path(update), upd_dir, keys, log=log)
        upd_ncas = sorted(p for p in upd_dir.glob("*.nca")
                          if not p.name.endswith(".cnmt.nca"))
        upd_types = _content_types(tools, upd_ncas, keys, log=log)
        update_program = _program_nca(upd_types)
        if update_program is None:
            result.warnings.append(
                f"{Path(update).name} has no Program content; ignoring it.")
        else:
            rights = upd_types[update_program]["rights_id"]
            if rights and rights.strip("0"):
                for ticket in upd_dir.glob("*.tik"):
                    titlekey = _titlekey_from_ticket(ticket)
                    if titlekey:
                        break
                if not titlekey:
                    titlekey = _titlekey_from_file(keys.title, rights)
                if not titlekey:
                    raise BackupError(
                        "the update needs a title key, but none was found: no "
                        "ticket in the .nsp and no matching entry in title.keys.")

    ui.step("Extracting the romfs")
    out_dir.mkdir(parents=True, exist_ok=True)
    args = ["-t", "nca"]
    if update_program is not None:
        args += ["--basenca", str(base_program), str(update_program)]
        result.used_update = True
    else:
        args += [str(base_program)]
    if titlekey:
        args += ["--titlekey", titlekey]
    args += ["--romfsdir", str(out_dir)]
    _run(tools, args, keys, log=log)

    if not config.looks_like_romfs(out_dir):
        raise BackupError(
            f"extraction finished but {out_dir} does not look like this game's "
            "romfs. See " + str(log))

    result.build_guid = config.build_guid(out_dir)
    detected = config.detect_release(out_dir)
    if detected:
        result.release = detected[1]
    shutil.rmtree(work, ignore_errors=True)
    return result
