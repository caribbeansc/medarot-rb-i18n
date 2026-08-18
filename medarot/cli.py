"""Command line interface: interactive menu plus one subcommand per action.

See ``docs/specs/SPEC-007-cli.md``. Exit codes: 0 success, 1 a step failed,
2 bad usage, 3 the game files are missing or unusable.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import build as build_mod
from . import catalog, config, csvio, extract, install as install_mod, lang, ui
from . import package as package_mod
from . import textures as textures_mod
from . import validate as validate_mod
from . import workspace as workspace_mod
from .config import ConfigError, Project
from .lang import LangError, LanguagePack
from .patch import metrics

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_NO_GAME = 3

TITLE = "MEDAROT CARD ROBATTLE RB: translation toolkit"


# ------------------------------------------------------------------ status --

def status_lines(project: Project) -> None:
    if project.has_romfs():
        ui.kv("Game files", str(project.romfs), status="ok")
        ui.kv("Release", f"{config.release_name(project.title_id)} "
                         f"({project.title_id})")
    else:
        ui.kv("Game files", "not configured: menu option 1", status="fail")

    if project.base_cache.exists():
        count = sum(1 for _ in project.base_cache.rglob("*") if _.is_file())
        ui.kv("Prepared", f"{count} files cached", status="ok")
    else:
        ui.kv("Prepared", "not yet (menu option 2). Latin text will look cramped",
              status="warn")

    inventory = extract.inventory_path(project, "tables")
    if inventory.exists():
        ui.kv("Extracted", f"yes: {project.work}", status="ok")
    else:
        ui.kv("Extracted", "not yet (menu option 3)", status="warn")

    packs = lang.discover(project.langs)
    if not packs:
        ui.kv("Languages", "none yet (menu option 7)", status="warn")
        return
    for pack in packs:
        stats = pack.stats()
        total = stats["text_total"] + stats["labels_total"]
        done = stats["text_translated"] + stats["labels_translated"]
        percent = f"{100.0 * done / total:.0f}%" if total else "-"
        ui.kv(f"  {pack.code}",
              f"{pack.name}: {done}/{total} strings ({percent}), "
              f"{stats['textures']} textures")


def _resolve_pack(project: Project, code: str | None) -> LanguagePack:
    if code:
        return lang.get(project.langs, code)
    packs = lang.discover(project.langs)
    if not packs:
        raise LangError(
            "no language packs in langs/: run:  mrb newlang <code> --name <name>")
    if len(packs) == 1:
        return packs[0]
    raise LangError("more than one language available: pass the code, e.g. "
                    f"'{packs[0].code}'")


def _pick_pack(project: Project, code: str | None = None) -> LanguagePack:
    """Like ``_resolve_pack`` but may ask, when there is a terminal."""
    if code:
        return lang.get(project.langs, code)
    packs = lang.discover(project.langs)
    if not packs:
        raise LangError("no language packs in langs/")
    if len(packs) == 1:
        return packs[0]
    return ui.choose(packs, "Language", labeller=lambda p: f"{p.code}: {p.name}")


# ---------------------------------------------------------------- commands --

def _extract_backup(project: Project, backup_path, update=None,
                    keys=None) -> str | None:
    """Decrypt a game backup into a romfs under work/, return that path.

    Used by both ``mrb setup --backup`` and the graphical patcher, so the two
    share exactly one extraction path.
    """
    from . import backup as backup_mod

    keys = keys or backup_mod.Keys.find(Path(backup_path).parent)
    if keys is None:
        raise backup_mod.BackupError(
            "no prod.keys found. Put it in ~/.switch or your emulator's key "
            "folder, or pass --keys /path/to/prod.keys.")
    out = project.work / "extracted_romfs"
    ui.heading(f"Extracting a romfs from {Path(backup_path).name}")
    ui.info(f"Using keys: {keys.prod}")
    result = backup_mod.extract(backup_path, out, keys=keys, update=update)
    for warning in result.warnings:
        ui.warn(warning)
    ui.ok(f"Extracted {result.release or 'romfs'} "
          f"({'with update' if result.used_update else 'base only'})")
    return str(out)


def cmd_backup(project: Project, args) -> int:
    from . import backup as backup_mod

    keys = None
    if getattr(args, "keys", None):
        prod = Path(args.keys)
        title = prod.parent / "title.keys"
        keys = backup_mod.Keys(prod, title if title.is_file() else None)
    try:
        romfs = _extract_backup(project, args.backup, args.update, keys)
    except backup_mod.BackupError as exc:
        ui.fail(str(exc))
        return EXIT_FAILED
    release = project.set_romfs(romfs)
    ui.ok(f"Game files: {project.romfs}")
    if release:
        ui.ok(f"Recognised {release}: mods will install under {project.title_id}")
    ui.info(f"Saved to {project.config_file.name}")
    return EXIT_OK


def cmd_setup(project: Project, args) -> int:
    if getattr(args, "title_id", None):
        project.set_title_id(args.title_id)
        ui.ok(f"Title id: {project.title_id}")
        if not args.romfs:
            return EXIT_OK
    romfs = args.romfs
    # A backup (.xci/.nsp/.xcz/.nsz) passed as --romfs is extracted first.
    if romfs:
        from . import backup as backup_mod
        if backup_mod.is_backup(romfs):
            try:
                romfs = _extract_backup(project, romfs)
            except backup_mod.BackupError as exc:
                ui.fail(str(exc))
                return EXIT_FAILED
    if not romfs:
        if not ui.is_tty():
            ui.fail("pass the romfs directory: mrb setup --romfs /path/to/romfs")
            return EXIT_USAGE
        ui.heading("Where are your extracted game files?")
        ui.info("Extract the romfs of your own dump (base + update) with hactoolnet,")
        ui.info("nsz, or your emulator's 'Extract Data > RomFS' menu entry.")
        ui.info("It is the folder that contains 'Data/StreamingAssets/'.")
        romfs = ui.ask("Path to romfs")
    try:
        release = project.set_romfs(romfs)
    except ConfigError as exc:
        ui.fail(str(exc))
        return EXIT_NO_GAME
    ui.ok(f"Game files: {project.romfs}")
    if release:
        ui.ok(f"Recognised {release}: mods will install under {project.title_id}")
    else:
        ui.warn(f"Release not recognised (build {config.build_guid(project.romfs)}); "
                f"keeping title id {project.title_id}.")
        ui.info("If this is the Kabuto release, run setup again with "
                "--title-id 0100DE4023982000, or the mod installs under the wrong "
                "game.")
    ui.info(f"Saved to {project.config_file.name}")
    return EXIT_OK


def cmd_status(project: Project, args) -> int:
    ui.banner(TITLE)
    status_lines(project)
    targets = config.detect_mod_targets(project.title_id)
    if targets:
        ui.kv("Emulators", ", ".join(sorted({t.emulator for t in targets})), status="ok")
    else:
        ui.kv("Emulators", "none detected: install with --to <dir>", status="warn")
    ui.out()
    return EXIT_OK


def cmd_prepare(project: Project, args) -> int:
    project.require_romfs()
    if project.base_cache.exists():
        ui.warn(f"This replaces the cache at {project.base_cache}")
        if not ui.confirm("Rebuild it?", True, assume_yes=args.yes):
            return EXIT_OK
        shutil.rmtree(project.base_cache)
    ui.info("This reads every bundle and every scene once. On a laptop it takes\n"
        "    somewhere between 20 minutes and an hour. It is only ever done once\n"
        "    per dump, and every language build reuses it.")
    results = metrics.prepare(project)
    for result in results:
        ui.ok(f"{result.name}: {result.summary()}")
    return EXIT_OK


def cmd_extract(project: Project, args) -> int:
    project.require_romfs()
    do_bundles = not args.tables_only
    summary = extract.refresh_all(project, tables=True, bundles=do_bundles,
                                  scenes=do_bundles)
    for key, value in summary.items():
        ui.ok(f"{key}: {value} strings")

    packs = lang.discover(project.langs)
    if args.lang:
        packs = [lang.get(project.langs, args.lang)]
    for pack in packs:
        space = workspace_mod.ensure(project, pack)
        counts = space.refresh()
        ui.ok(f"{pack.code}: working copy at {space.root}")
        workspace_mod.report(counts)
    return EXIT_OK


def cmd_sync(project: Project, args) -> int:
    pack = _resolve_pack(project, args.lang)
    space = workspace_mod.ensure(project, pack)
    counts = space.sync()
    ui.ok(f"{pack.code}: {counts['translations']} translations published to "
          f"{pack.directory}")
    workspace_mod.report(counts)
    return EXIT_OK


def cmd_validate(project: Project, args) -> int:
    pack = _resolve_pack(project, args.lang)
    space = workspace_mod.ensure(project, pack)
    report = validate_mod.run(pack, space if space.exists() else None)

    for note in report.skipped_checks:
        ui.warn(f"skipped: {note}")
    for finding in report.warnings:
        ui.out("  " + finding.line())
    for finding in report.errors:
        ui.out("  " + finding.line())

    ui.out()
    ui.info(f"{report.checked} translations checked, {report.empty} still empty, "
            f"{len(report.errors)} errors, {len(report.warnings)} warnings")
    return EXIT_OK if report.ok(strict=args.strict) else EXIT_FAILED


def cmd_build(project: Project, args) -> int:
    pack = _resolve_pack(project, args.lang)
    report = build_mod.run(
        project, pack,
        only=args.only.split(",") if args.only else None,
        skip=args.skip.split(",") if args.skip else None,
        ascii_mode=args.ascii,
        keep=args.keep,
        allow_stale=args.allow_stale,
    )
    ui.out()
    for warning in report.warnings:
        ui.warn(warning)
    if not report.ok():
        ui.fail("nothing was applied: is anything translated yet?")
        return EXIT_FAILED
    ui.ok(f"{report.applied} strings/textures in {report.files} files")
    ui.ok(f"Mod: {report.mod_dir}")
    for line in build_mod.describe_mod(report.mod_dir):
        ui.detail(line)
    ui.info(f"Install it with:  mrb install {pack.code}")
    return EXIT_OK


def cmd_install(project: Project, args) -> int:
    pack = _resolve_pack(project, args.lang)

    if getattr(args, "sd", None):
        target = package_mod.relative_root(pack, package_mod.ATMOSPHERE)
        ui.heading("This will replace")
        ui.info(str(Path(args.sd) / target))
        if not ui.confirm("Continue?", True, assume_yes=args.yes or not ui.is_tty()):
            return EXIT_OK
        result = package_mod.install_to_sd(project, pack, args.sd)
        ui.ok(f"{result.files} files -> {result.romfs}")
        ui.info("Atmosphère picks it up next time you launch the game.")
        return EXIT_OK

    plan = install_mod.plan(project, pack, args.to)
    if not plan:
        ui.fail("no emulator detected. Pass one with --to <mods dir>")
        return EXIT_FAILED
    ui.heading("This will replace")
    for target, destination in plan:
        ui.info(f"{target.emulator}: {destination}")
    if not ui.confirm("Continue?", True, assume_yes=args.yes or not ui.is_tty()):
        return EXIT_OK
    done = install_mod.install(project, pack, args.to)
    for item in done:
        ui.ok(f"{item.emulator}: {item.files} files -> {item.path}")
    ui.info("Enable mods for the game in your emulator, then start it.")
    return EXIT_OK


def cmd_package(project: Project, args) -> int:
    pack = _resolve_pack(project, args.lang)
    formats = (package_mod.FORMATS if args.format in (None, "both")
               else (args.format,))
    packages = package_mod.build_all(project, pack, formats,
                                     make_archive=args.zip)
    for item in packages:
        ui.ok(f"{item.format}: {item.files} files -> {item.root}")
        ui.detail(item.where())
        if item.archive:
            size = item.archive.stat().st_size / 1_048_576
            ui.detail(f"zip: {item.archive} ({size:.1f} MB)")
    return EXIT_OK


def cmd_uninstall(project: Project, args) -> int:
    pack = _resolve_pack(project, args.lang)
    plan = install_mod.plan(project, pack, args.to)
    existing = [dest for _, dest in plan if dest.exists()]
    if not existing:
        ui.info("nothing installed")
        return EXIT_OK
    for destination in existing:
        ui.info(f"will delete {destination}")
    if not ui.confirm("Delete?", False, assume_yes=args.yes):
        return EXIT_OK
    for destination in install_mod.uninstall(project, pack, args.to):
        ui.ok(f"removed {destination}")
    return EXIT_OK


def cmd_newlang(project: Project, args) -> int:
    name = args.name
    if not name:
        if not ui.is_tty():
            ui.fail("pass --name")
            return EXIT_USAGE
        name = ui.ask("Language name, as speakers write it (e.g. Français)")
    template = None
    if args.like:
        template = lang.get(project.langs, args.like)
    elif ui.is_tty():
        packs = lang.discover(project.langs)
        if packs and ui.confirm("Copy the key list from an existing language?", True):
            template = ui.choose(packs, "Copy keys from",
                                 labeller=lambda p: f"{p.code}: {p.name}")
    pack = lang.create(project.langs, args.code, name, template=template)
    ui.ok(f"Created {pack.directory}")
    ui.info("Next:  mrb extract --lang " + pack.code)
    ui.info("Then edit the 't' fields in " + str(project.work_lang(pack.code)))
    return EXIT_OK


def cmd_textures(project: Project, args) -> int:
    pack = _resolve_pack(project, args.lang)
    if args.import_png:
        result = textures_mod.import_edited(project, pack, args.import_png, args.name)
        ui.ok(f"{result.name}: {result.percent:.1f}% of the pixels changed")
        if not result.fits():
            ui.warn(f"your text reaches the {', '.join(result.touches)} edge(s) of "
                    f"the texture, where the original had nothing: the game will "
                    f"most likely clip it. Shorten the line rather than shrinking "
                    f"the letters.")
        ui.info(f"delta: {result.delta}")
        ui.info(f"mask:  {result.mask}")
        ui.info(f"Check it with:  mrb textures {pack.code} --preview {result.name}")
        return EXIT_OK
    if args.preview:
        path = textures_mod.preview(project, pack, args.preview)
        ui.ok(f"wrote {path}")
        return EXIT_OK

    rows = textures_mod.status(project, pack)
    if not rows:
        ui.info(f"{pack.code} has no translated textures yet.")
        ui.info("Export one, edit it, then import it:")
        ui.detail("mrb assets --name Card_Change")
        ui.detail(f"mrb textures {pack.code} --import work/assets/dlg/Card_Change.png")
        return EXIT_OK
    ui.table([(r["texture"], "yes" if r["delta"] else "-", r["size"], r["format"],
               r["copies"], r["text"][:32]) for r in rows],
             headers=["texture", "delta", "size", "format", "copies", "says"])
    ui.info(f"{sum(1 for r in rows if r['delta'])}/{len(rows)} have a delta in "
            f"{pack.delta_dir}")
    return EXIT_OK


def cmd_assets(project: Project, args) -> int:
    project.require_romfs()
    if args.list:
        index = extract.texture_index(project, refresh=args.refresh)
        rows = [(name, f"{e['width']}x{e['height']}", e["format"],
                 "yes" if e.get("swizzle_bug") else "", len(e["containers"]))
                for name, e in sorted(index.items())
                if not args.filter or args.filter.lower() in name.lower()]
        ui.table(rows[:args.limit],
                 headers=["texture", "size", "format", "swizzle bug", "copies"])
        ui.info(f"{len(rows)} textures matched, showing up to {args.limit}")
        return EXIT_OK
    written = extract.export_textures(
        project,
        names=args.name.split(",") if args.name else None,
        groups=args.group.split(",") if args.group else None)
    ui.ok(f"{written} PNGs under {project.assets_dir}")
    return EXIT_OK


def cmd_csv(project: Project, args) -> int:
    pack = _resolve_pack(project, args.lang)
    space = workspace_mod.ensure(project, pack)
    if not space.exists():
        ui.fail("no working copy yet: run:  mrb extract")
        return EXIT_FAILED
    if args.import_file:
        report = csvio.import_csv(space, args.import_file)
        ui.ok(f"{report.applied} translations imported, {report.unchanged} unchanged, "
              f"{report.unknown} keys not in this dump")
        ui.info(f"Publish them with:  mrb sync {pack.code}")
        return EXIT_OK
    dest = Path(args.out) if args.out else project.work / f"{pack.code}.csv"
    rows = csvio.export(space, dest, pending_only=args.pending)
    ui.ok(f"{rows} rows -> {dest}")
    ui.info("Edit the 'translation' column, then:  mrb csv "
            f"{pack.code} --import {dest}")
    return EXIT_OK


def cmd_doctor(project: Project, args) -> int:
    problems = 0
    ui.heading("Environment")
    ui.info(f"python {sys.version.split()[0]} at {sys.executable}")
    for module in ("UnityPy", "PIL"):
        try:
            imported = __import__(module)
            version = getattr(imported, "__version__", "?")
            ui.ok(f"{module} {version}")
        except ImportError:
            ui.fail(f"{module} is missing: pip install -r requirements.txt")
            problems += 1

    ui.heading("Game files")
    if project.has_romfs():
        tables = list(project.tables_dir.glob("IdxRes_*.bytes"))
        bundles = project.bundles()
        ui.ok(f"{len(tables)} data tables, {len(bundles)} bundles, "
              f"{len(project.scenes())} scene files")
    else:
        ui.fail("no romfs configured")
        problems += 1

    ui.heading("Language packs")
    for pack in lang.discover(project.langs):
        offenders = catalog.scan_tree_for_source_text(pack.directory)
        if offenders:
            ui.fail(f"{pack.code}: source text in {len(offenders)} file(s) "
                    f"(SPEC-005/R-4): {offenders[0]}")
            problems += 1
        else:
            ui.ok(f"{pack.code}: no source text, safe to publish")

    ui.heading("Emulators")
    ui.info(f"{config.release_name(project.title_id)}: title id {project.title_id}")
    targets = config.detect_mod_targets(project.title_id)
    if targets:
        for target in targets:
            ui.ok(f"{target.emulator} ({target.style}): {target.path}")
    else:
        ui.warn("none detected; use 'mrb install <lang> --to <dir>'")

    if args.textures and project.has_romfs():
        ui.heading("Textures affected by the UnityPy swizzle bug")
        index = extract.texture_index(project, refresh=args.refresh)
        affected = [n for n, e in index.items() if e.get("swizzle_bug")]
        ui.info(f"{len(affected)} of {len(index)}: {', '.join(sorted(affected)[:12])}")

    ui.out()
    if problems:
        ui.fail(f"{problems} problem(s) found")
        return EXIT_FAILED
    ui.ok("all good")
    return EXIT_OK


# --------------------------------------------------------- interactive edit --

def edit_loop(project: Project, pack: LanguagePack) -> int:
    space = workspace_mod.ensure(project, pack)
    if not space.exists():
        ui.fail("no working copy yet: run option 3 (extract) first")
        return EXIT_FAILED

    pending = space.pending()
    if not pending:
        ui.ok(f"{pack.name}: nothing left to translate")
        return EXIT_OK

    ui.heading(f"{pack.name}: {len(pending)} strings left")
    ui.info("Type the translation and press enter. Empty line skips.")
    ui.info("Commands:  .q quit and save   .s skip table   .h help")

    dirty: dict[str, tuple] = {}
    edited = 0
    current_table = None
    try:
        for where, entry in pending:
            if current_table != where:
                current_table = where
                ui.out()
                ui.out("  " + ui.paint(f"[{where}]", ui.BOLD))
            source = entry.get("jp", "")
            ui.out()
            ui.out(f"  source : {ui.paint(source, ui.CYAN)}")
            if entry.get("note"):
                ui.out(f"  note   : {entry['note']}")
            if entry.get("seen"):
                ui.out(f"  used   : {entry['seen']} time(s)")
            answer = ui.ask("       →")
            if answer == ".q":
                break
            if answer == ".s":
                current_table = None
                continue
            if answer == ".h":
                ui.info("Keep {0} placeholders and <tags> exactly as they are.")
                ui.info("Use \\n for a line break.")
                continue
            if not answer:
                continue
            key = catalog.entry_key(entry, catalog.KIND_LABELS
                                    if where == "labels" else catalog.KIND_IDXRES)
            space.set_translation(where, key, answer.replace("\\n", "\n"))
            edited += 1
    except ui.Aborted:
        pass

    ui.out()
    ui.ok(f"{edited} translations saved to {space.root}")
    if edited:
        ui.info(f"Publish them with:  mrb sync {pack.code}")
    return EXIT_OK


# ------------------------------------------------------------------- menu ----

def menu_translate(project: Project) -> None:
    try:
        pack = _pick_pack(project)
    except LangError as exc:
        ui.fail(str(exc))
        return
    stats = pack.stats()
    ui.heading(f"{pack.name} ({pack.code})")
    ui.info(f"{stats['text_translated']}/{stats['text_total']} table strings, "
            f"{stats['labels_translated']}/{stats['labels_total']} labels, "
            f"{stats['textures']} textures")
    choice = ui.menu(
        [("1", "Translate here", "one string at a time, in the terminal"),
         ("2", "Export a spreadsheet", "CSV you can edit in Excel"),
         ("3", "Import a spreadsheet", "read a CSV back"),
         ("4", "Publish (sync)", "work/ -> langs/, drops source text"),
         ("5", "Check it (validate)", "")],
        quit_key="0", quit_label="Back")
    if choice == "1":
        edit_loop(project, pack)
    elif choice == "2":
        cmd_csv(project, argparse.Namespace(
            lang=pack.code, import_file=None, out=None, pending=True))
    elif choice == "3":
        path = ui.ask("Path to the CSV")
        if path:
            cmd_csv(project, argparse.Namespace(
                lang=pack.code, import_file=path, out=None, pending=False))
    elif choice == "4":
        cmd_sync(project, argparse.Namespace(lang=pack.code))
    elif choice == "5":
        cmd_validate(project, argparse.Namespace(lang=pack.code, strict=False))


def interactive(project: Project) -> int:
    while True:
        ui.banner(TITLE, "fan translation toolkit: your dump stays on your machine")
        status_lines(project)
        choice = ui.menu([
            ("1", "Point me at the game", "set the romfs folder"),
            ("2", "Prepare game files", "one-off, 20-60 min"),
            ("3", "Read the game's text", "extract tables, labels, textures"),
            ("4", "Translate", "edit text, spreadsheets, publish"),
            ("5", "Build a mod", ""),
            ("6", "Install into an emulator", ""),
            ("7", "Package for sharing", "emulator folder and Atmosphère SD zip"),
            ("8", "Add a language", ""),
            ("9", "Diagnose", "check tools, dump and packs"),
        ])
        try:
            if choice == "0":
                ui.out()
                return EXIT_OK
            if choice == "1":
                cmd_setup(project, argparse.Namespace(romfs=None, title_id=None))
                project = config.load(project.root)
            elif choice == "2":
                cmd_prepare(project, argparse.Namespace(yes=False))
            elif choice == "3":
                cmd_extract(project, argparse.Namespace(lang=None, tables_only=False))
            elif choice == "4":
                menu_translate(project)
            elif choice == "5":
                pack = _pick_pack(project)
                cmd_build(project, argparse.Namespace(
                    lang=pack.code, only=None, skip=None, ascii=False,
                    keep=False, allow_stale=False))
            elif choice == "6":
                pack = _pick_pack(project)
                cmd_install(project, argparse.Namespace(
                    lang=pack.code, to=None, sd=None, yes=False))
            elif choice == "7":
                pack = _pick_pack(project)
                cmd_package(project, argparse.Namespace(
                    lang=pack.code, format="both", zip=True))
            elif choice == "8":
                code = ui.ask("Language code (es, fr, pt-br…)")
                if code:
                    cmd_newlang(project, argparse.Namespace(
                        code=code, name=None, like=None))
            elif choice == "9":
                cmd_doctor(project, argparse.Namespace(textures=False, refresh=False))
        except ui.Aborted:
            ui.out()
            ui.info("cancelled")
        except (ConfigError, LangError, workspace_mod.WorkspaceError,
                build_mod.BuildError, install_mod.InstallError,
                csvio.CsvError, textures_mod.TextureError, extract.ExtractError,
                package_mod.PackageError) as exc:
            ui.fail(str(exc))
        ui.pause()


# ----------------------------------------------------------------- parser ----

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mrb", description=TITLE,
        epilog="Run with no arguments for the interactive menu.")
    sub = parser.add_subparsers(dest="command")

    setup = sub.add_parser("setup", help="tell the tool where your romfs is")
    setup.add_argument("--romfs", help="path to the extracted romfs, or a backup "
                       "(.xci/.nsp/.xcz/.nsz) to extract it from")
    setup.add_argument("--title-id", dest="title_id",
                       help="install under a different title (e.g. the Kabuto version)")
    setup.set_defaults(func=cmd_setup)

    backup = sub.add_parser("backup", help="extract a romfs from a game backup "
                            "(.xci/.nsp/.xcz/.nsz) with your own keys")
    backup.add_argument("backup", help="the base backup (a cartridge dump or eShop .nsp)")
    backup.add_argument("--update", help="an update .nsp to layer on top")
    backup.add_argument("--keys", help="path to prod.keys (else auto-detected)")
    backup.set_defaults(func=cmd_backup)

    status = sub.add_parser("status", help="show what is configured and how far along")
    status.set_defaults(func=cmd_status)

    prepare = sub.add_parser("prepare", help="build the language-independent cache")
    prepare.add_argument("--yes", action="store_true", help="do not ask")
    prepare.set_defaults(func=cmd_prepare)

    extract_cmd = sub.add_parser("extract", help="read text out of your own dump")
    extract_cmd.add_argument("--lang", help="only refresh this language's working copy")
    extract_cmd.add_argument("--tables-only", action="store_true",
                             help="skip the slow bundle and scene scans")
    extract_cmd.set_defaults(func=cmd_extract)

    sync = sub.add_parser("sync", help="publish work/ into langs/ without source text")
    sync.add_argument("lang", nargs="?")
    sync.set_defaults(func=cmd_sync)

    validate = sub.add_parser("validate", help="check a translation")
    validate.add_argument("lang", nargs="?")
    validate.add_argument("--strict", action="store_true",
                          help="treat warnings as errors")
    validate.set_defaults(func=cmd_validate)

    build_cmd = sub.add_parser("build", help="build the LayeredFS mod")
    build_cmd.add_argument("lang", nargs="?")
    build_cmd.add_argument("--only", help=f"comma-separated: {','.join(build_mod.STEPS)}")
    build_cmd.add_argument("--skip", help="comma-separated steps to skip")
    build_cmd.add_argument("--ascii", action="store_true",
                           help="degrade accents using the pack's ascii_fallback")
    build_cmd.add_argument("--keep", action="store_true",
                           help="do not wipe the previous build")
    build_cmd.add_argument("--allow-stale", action="store_true",
                           help="apply translations whose source text changed")
    build_cmd.set_defaults(func=cmd_build)

    install = sub.add_parser("install", help="copy the mod into your emulator(s)")
    install.add_argument("lang", nargs="?")
    install.add_argument("--to", help="mods directory to install into")
    install.add_argument("--sd", help="root of a mounted SD card (Atmosphère layout)")
    install.add_argument("--yes", action="store_true")
    install.set_defaults(func=cmd_install)

    package = sub.add_parser(
        "package", help="stage the mod for emulators and/or Atmosphère")
    package.add_argument("lang", nargs="?")
    package.add_argument("--format", choices=[*package_mod.FORMATS, "both"],
                         default="both")
    package.add_argument("--zip", action="store_true", help="also make a zip")
    package.set_defaults(func=cmd_package)

    uninstall = sub.add_parser("uninstall", help="remove the mod from your emulator(s)")
    uninstall.add_argument("lang", nargs="?")
    uninstall.add_argument("--to")
    uninstall.add_argument("--yes", action="store_true")
    uninstall.set_defaults(func=cmd_uninstall)

    newlang = sub.add_parser("newlang", help="create a new language pack")
    newlang.add_argument("code", help="es, fr, pt-br…")
    newlang.add_argument("--name", help="how speakers write the language name")
    newlang.add_argument("--like", help="copy the key list from this language")
    newlang.set_defaults(func=cmd_newlang)

    textures = sub.add_parser(
        "textures", help="import your edited artwork as a delta, or list what exists")
    textures.add_argument("lang", nargs="?")
    textures.add_argument("--import", dest="import_png",
                          help="an edited PNG to store as a delta")
    textures.add_argument("--name",
                          help="texture name, if the PNG file is named differently")
    textures.add_argument("--preview",
                          help="rebuild the final texture for this name, to look at it")
    textures.set_defaults(func=cmd_textures)

    assets = sub.add_parser("assets", help="list or export the game's textures")
    assets.add_argument("--list", action="store_true", help="list instead of exporting")
    assets.add_argument("--filter", help="substring of the texture name")
    assets.add_argument("--name", help="export only these (comma-separated)")
    assets.add_argument("--group", help="export only these groups (comma-separated)")
    assets.add_argument("--limit", type=int, default=60)
    assets.add_argument("--refresh", action="store_true", help="rebuild the index")
    assets.set_defaults(func=cmd_assets)

    csv_cmd = sub.add_parser("csv", help="export/import a spreadsheet")
    csv_cmd.add_argument("lang", nargs="?")
    csv_cmd.add_argument("--out", help="where to write the CSV")
    csv_cmd.add_argument("--import", dest="import_file", help="read this CSV back")
    csv_cmd.add_argument("--pending", action="store_true",
                         help="export only untranslated rows")
    csv_cmd.set_defaults(func=cmd_csv)

    doctor = sub.add_parser("doctor", help="check tools, dump and language packs")
    doctor.add_argument("--textures", action="store_true",
                        help="also audit textures for the UnityPy swizzle bug")
    doctor.add_argument("--refresh", action="store_true")
    doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    project = config.load()

    if not argv:
        if ui.is_tty():
            try:
                return interactive(project)
            except ui.Aborted:
                ui.out()
                return EXIT_OK
        return cmd_status(project, None)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return EXIT_USAGE

    try:
        return args.func(project, args)
    except ui.Aborted:
        ui.out()
        return EXIT_OK
    except ConfigError as exc:
        ui.fail(str(exc))
        return EXIT_NO_GAME
    except (LangError, workspace_mod.WorkspaceError, build_mod.BuildError,
            install_mod.InstallError, csvio.CsvError, textures_mod.TextureError,
            extract.ExtractError, catalog.CatalogError,
            package_mod.PackageError) as exc:
        ui.fail(str(exc))
        return EXIT_FAILED
