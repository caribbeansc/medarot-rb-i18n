"""Graphical patcher: pick your romfs, pick a language, click Patch.

A thin Tkinter shell over the same code the CLI uses, so a non-technical
player can build and install the mod with two clicks. Built into standalone
Windows/macOS executables by ``.github/workflows/patcher.yml``; running
``python gui.py`` from a checkout works exactly the same.

Frozen-app layout: the repo's ``langs/`` ships inside the executable and is
copied on launch into a per-user folder (``~/MedarotRB``), which then holds
the configuration, the ``work/`` caches and the built mods. Nothing from the
game is ever bundled: the user always points the app at their own dump.
"""
from __future__ import annotations

import argparse
import locale
import queue
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
FROZEN = hasattr(sys, "_MEIPASS")
USER_ROOT = Path.home() / "MedarotRB" if FROZEN else BUNDLE_DIR

sys.path.insert(0, str(BUNDLE_DIR))

SPANISH = (locale.getlocale()[0] or "").lower().startswith("es")


def tr(en: str, es: str) -> str:
    return es if SPANISH else en


PROGRESS_RE = re.compile(r"^\s{2,}\S.*: \d+(/\d+)?(\s|$)")


class LogSink:
    """File-like stdout replacement feeding the log widget through a queue."""

    def __init__(self, q: queue.Queue):
        self.q = q
        self._buf = ""

    def write(self, text: str) -> int:
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self.q.put(line.replace("\r", ""))
        return len(text)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Medarot RB Patcher")
        root.geometry("720x520")
        root.minsize(560, 420)

        self.q: queue.Queue = queue.Queue()
        self.busy = False

        frame = ttk.Frame(root, padding=10)
        frame.pack(fill="both", expand=True)

        row = ttk.Frame(frame)
        row.pack(fill="x")
        ttk.Label(row, text=tr("Game files (romfs):", "Archivos del juego (romfs):")).pack(side="left")
        self.romfs_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.romfs_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row, text=tr("Browse…", "Elegir…"), command=self.pick_romfs).pack(side="left")

        hint = tr("The folder that contains Data/StreamingAssets — extract it from "
                  "YOUR OWN dump with your emulator's 'Extract Data > RomFS'.",
                  "La carpeta que contiene Data/StreamingAssets — extráela de TU "
                  "PROPIO volcado con 'Extract Data > RomFS' en tu emulador.")
        ttk.Label(frame, text=hint, foreground="#666", wraplength=680).pack(fill="x", pady=(2, 8))

        row2 = ttk.Frame(frame)
        row2.pack(fill="x", pady=(0, 8))
        ttk.Label(row2, text=tr("Language:", "Idioma:")).pack(side="left")
        self.lang_var = tk.StringVar()
        self.lang_box = ttk.Combobox(row2, textvariable=self.lang_var, state="readonly", width=28)
        self.lang_box.pack(side="left", padx=6)

        self.btn_patch = ttk.Button(
            row2, text=tr("1 · Build the patch", "1 · Crear el parche"),
            command=lambda: self.launch(self.job_patch))
        self.btn_patch.pack(side="left", padx=4)
        self.btn_install = ttk.Button(
            row2, text=tr("2 · Install into emulator", "2 · Instalar en el emulador"),
            command=lambda: self.launch(self.job_install))
        self.btn_install.pack(side="left", padx=4)
        self.btn_zip = ttk.Button(
            row2, text=tr("or ZIP for SD card", "o ZIP para tarjeta SD"),
            command=lambda: self.launch(self.job_package))
        self.btn_zip.pack(side="left", padx=4)

        self.log = tk.Text(frame, wrap="none", state="disabled", height=18,
                           background="#111", foreground="#ddd")
        self.log.pack(fill="both", expand=True)

        self.status = tk.StringVar(value=tr("Ready.", "Listo."))
        ttk.Label(frame, textvariable=self.status).pack(fill="x", pady=(6, 0))

        self._last_progress = False
        root.after(100, self.drain)
        self.load_state()

    # ---------------------------------------------------------------- state --
    def project(self):
        from medarot import config
        USER_ROOT.mkdir(parents=True, exist_ok=True)
        return config.load(USER_ROOT)

    def load_state(self) -> None:
        try:
            if FROZEN:  # refresh the shipped translations into the user folder
                target = USER_ROOT / "langs"
                USER_ROOT.mkdir(parents=True, exist_ok=True)
                if (BUNDLE_DIR / "langs").is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                    shutil.copytree(BUNDLE_DIR / "langs", target)
            from medarot import lang
            project = self.project()
            packs = lang.discover(project.langs)
            names = [f"{p.name} ({p.code})" for p in packs]
            self.packs = packs
            self.lang_box["values"] = names
            if names:
                self.lang_box.current(0)
            if project.has_romfs():
                self.romfs_var.set(str(project.romfs))
        except Exception as exc:  # never die on startup
            self.put_log(f"!! {exc}")

    def pack_code(self) -> str:
        idx = self.lang_box.current()
        return self.packs[idx].code if idx >= 0 else "es"

    def pick_romfs(self) -> None:
        path = filedialog.askdirectory(title="romfs")
        if path:
            self.romfs_var.set(path)

    # ------------------------------------------------------------------ log --
    def put_log(self, line: str) -> None:
        self.q.put(line)

    def drain(self) -> None:
        try:
            while True:
                line = self.q.get_nowait()
                is_progress = bool(PROGRESS_RE.match(line))
                self.log.configure(state="normal")
                if is_progress and self._last_progress:
                    self.log.delete("end-2l", "end-1l")
                self.log.insert("end", line + "\n")
                self.log.see("end")
                self.log.configure(state="disabled")
                self._last_progress = is_progress
        except queue.Empty:
            pass
        self.root.after(100, self.drain)

    # ------------------------------------------------------------------ jobs --
    def launch(self, job) -> None:
        if self.busy:
            return
        romfs = self.romfs_var.get().strip()
        if not romfs:
            messagebox.showinfo("Medarot RB Patcher",
                                tr("Pick your romfs folder first.",
                                   "Primero elige tu carpeta romfs."))
            return
        self.busy = True
        for b in (self.btn_patch, self.btn_install, self.btn_zip):
            b.state(["disabled"])
        self.status.set(tr("Working… this window may look frozen during long steps.",
                           "Trabajando… la ventana puede parecer congelada en pasos largos."))
        threading.Thread(target=self._run, args=(job,), daemon=True).start()

    def _run(self, job) -> None:
        sink = LogSink(self.q)
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = sink
        try:
            job()
        except Exception as exc:
            print(f"!! {type(exc).__name__}: {exc}")
        finally:
            sink.write("\n")
            sys.stdout, sys.stderr = old_out, old_err
            self.root.after(0, self._done)

    def _done(self) -> None:
        self.busy = False
        for b in (self.btn_patch, self.btn_install, self.btn_zip):
            b.state(["!disabled"])
        self.status.set(tr("Done — see the log above.", "Hecho — revisa el registro."))

    def _setup(self, cli, project) -> bool:
        code = cli.cmd_setup(project, argparse.Namespace(
            romfs=self.romfs_var.get().strip(), title_id=None))
        return code == cli.EXIT_OK

    def job_patch(self) -> None:
        from medarot import cli
        project = self.project()
        if not self._setup(cli, project):
            return
        project = self.project()
        if not project.base_cache.exists():
            print(tr("First time with this dump: preparing the text-metrics cache.",
                     "Primera vez con este volcado: preparando la caché de métricas."))
            print(tr("This runs ONCE and takes 20-60 minutes. Leave the window open.",
                     "Se hace UNA vez y tarda 20-60 minutos. Deja la ventana abierta."))
            cli.cmd_prepare(project, argparse.Namespace(yes=True))
        cli.cmd_build(project, argparse.Namespace(
            lang=self.pack_code(), only=None, skip=None, ascii=False,
            keep=False, allow_stale=False))

    def job_install(self) -> None:
        from medarot import cli
        project = self.project()
        if not self._setup(cli, project):
            return
        cli.cmd_install(self.project(), argparse.Namespace(
            lang=self.pack_code(), sd=None, to=None, yes=True))

    def job_package(self) -> None:
        from medarot import cli
        project = self.project()
        if not self._setup(cli, project):
            return
        cli.cmd_package(self.project(), argparse.Namespace(
            lang=self.pack_code(), format=None, zip=True))
        out = self.project().build / self.pack_code()
        print(tr(f"ZIPs are in: {out}", f"Los ZIP están en: {out}"))
        self.root.after(0, lambda: self._reveal(out))

    @staticmethod
    def _reveal(path: Path) -> None:
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            elif sys.platform.startswith("win"):
                subprocess.Popen(["explorer", str(path)])
        except Exception:
            pass


def main() -> None:
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
