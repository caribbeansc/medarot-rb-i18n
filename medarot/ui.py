"""Terminal output and prompts, with no third-party dependencies.

Numeric menus only: no arrow keys, no curses, no raw mode, so it behaves the same
in Windows ``cmd.exe``, over SSH and in a CI log (SPEC-007/R-3, R-4).
"""

from __future__ import annotations

import os
import shutil
import sys

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
CYAN = "\033[36m"
GREY = "\033[90m"


class Aborted(Exception):
    """The user pressed Ctrl-C or Ctrl-D at a prompt (SPEC-007/R-9)."""


def _enable_windows_vt() -> bool:
    """Turn on ANSI escape processing on legacy Windows consoles."""
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING on stdout
        return bool(kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7))
    except Exception:
        return False


def is_tty() -> bool:
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def use_colour() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    if not is_tty():
        return False
    return _enable_windows_vt()


_COLOUR = None


def colour_enabled() -> bool:
    global _COLOUR
    if _COLOUR is None:
        _COLOUR = use_colour()
    return _COLOUR


def paint(text: str, *codes: str) -> str:
    if not codes or not colour_enabled():
        return text
    return "".join(codes) + text + RESET


def width(default: int = 80) -> int:
    try:
        return max(40, min(shutil.get_terminal_size((default, 24)).columns, 100))
    except Exception:
        return default


# ------------------------------------------------------------------ output --

def out(text: str = "") -> None:
    print(text)


def heading(text: str) -> None:
    out()
    out(paint(text, BOLD))
    out(paint("─" * min(len(text), width()) if colour_enabled() else "-" * len(text), GREY))


def banner(title: str, subtitle: str = "") -> None:
    out()
    out("  " + paint(title, BOLD, CYAN))
    if subtitle:
        out("  " + paint(subtitle, GREY))
    out()


def ok(text: str) -> None:
    out(f"  {paint('✓', GREEN)} {text}")


def warn(text: str) -> None:
    out(f"  {paint('!', YELLOW)} {text}")


def fail(text: str) -> None:
    out(f"  {paint('✗', RED)} {text}")


def info(text: str) -> None:
    out(f"  {paint('·', GREY)} {text}")


def step(text: str) -> None:
    out()
    out(f"{paint('▶', BLUE)} {paint(text, BOLD)}")


def detail(text: str) -> None:
    out(f"    {paint(text, GREY)}")


def kv(key: str, value: str, *, status: str = "") -> None:
    marks = {"ok": paint("✓", GREEN), "warn": paint("!", YELLOW),
             "fail": paint("✗", RED), "": " "}
    out(f"  {marks.get(status, ' ')} {key:<14}{value}")


def bullets(items) -> None:
    for item in items:
        out(f"    - {item}")


def table(rows, headers=None) -> None:
    """Plain aligned text table; no box drawing so it survives redirection."""
    rows = [[str(c) for c in row] for row in rows]
    if headers:
        rows = [[str(h) for h in headers]] + rows
    if not rows:
        return
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    for index, row in enumerate(rows):
        line = "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip()
        if headers and index == 0:
            out("  " + paint(line, BOLD))
            out("  " + paint("-" * len(line), GREY))
        else:
            out("  " + line)


class Progress:
    """One line of progress, rewritten in place on a TTY and appended elsewhere.

    Correctness never depends on cursor tricks (SPEC-007/R-8).
    """

    def __init__(self, label: str, total: int | None = None, *, every: int = 1):
        self.label = label
        self.total = total
        self.every = max(1, every)
        self.count = 0
        self._tty = is_tty()

    def advance(self, note: str = "") -> None:
        self.count += 1
        if self.count % self.every and self.count != self.total:
            return
        if self.total:
            text = f"    {self.label}: {self.count}/{self.total}"
        else:
            text = f"    {self.label}: {self.count}"
        if note:
            text += f"  {note}"
        if self._tty:
            sys.stdout.write("\r" + text[:width() - 1].ljust(width() - 1))
            sys.stdout.flush()
        else:
            print(text)

    def done(self, note: str = "") -> None:
        if self._tty:
            sys.stdout.write("\r" + " " * (width() - 1) + "\r")
            sys.stdout.flush()
        if note:
            detail(note)


# ------------------------------------------------------------------ input ---

def _read(prompt: str) -> str:
    try:
        return input(prompt)
    except (KeyboardInterrupt, EOFError) as exc:
        out()
        raise Aborted() from exc


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    answer = _read(f"  {prompt}{suffix}: ").strip()
    return answer or default


def confirm(prompt: str, default: bool = False, *, assume_yes: bool = False) -> bool:
    """Ask a yes/no question. ``assume_yes`` pre-answers it (SPEC-007/R-5)."""
    if assume_yes:
        out(f"  {prompt} [y/n]: y (--yes)")
        return True
    hint = "Y/n" if default else "y/N"
    while True:
        answer = _read(f"  {prompt} [{hint}]: ").strip().lower()
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        warn("Please answer y or n.")


def menu(options, prompt: str = "Choose", *, quit_key: str = "0",
         quit_label: str = "Quit") -> str:
    """Show a numbered menu and return the chosen key.

    ``options`` is a list of ``(key, label, description)`` triples.
    """
    out()
    for key, label, description in options:
        line = f"  {paint(key, BOLD)}  {label}"
        if description:
            pad = " " * max(1, 22 - len(label))
            line += f"{pad}{paint(description, GREY)}"
        out(line)
    if quit_key is not None:
        out(f"  {paint(quit_key, BOLD)}  {quit_label}")
    out()
    valid = {key for key, _, _ in options}
    if quit_key is not None:
        valid.add(quit_key)
    while True:
        answer = _read(f"  {prompt} > ").strip()
        if answer in valid:
            return answer
        warn(f"Type one of: {', '.join(sorted(valid))}")


def choose(items, prompt: str = "Choose", *, labeller=str) -> object:
    """Pick one item from a list; returns the item itself."""
    options = [(str(i + 1), labeller(item), "") for i, item in enumerate(items)]
    key = menu(options, prompt, quit_key=None)
    return items[int(key) - 1]


def pause() -> None:
    if is_tty():
        try:
            input(paint("\n  (enter to continue)", GREY))
        except (KeyboardInterrupt, EOFError):
            out()
