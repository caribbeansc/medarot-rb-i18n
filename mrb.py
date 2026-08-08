#!/usr/bin/env python3
"""Entry point: run ``python mrb.py`` for the interactive menu.

Kept deliberately tiny so that a double-click or a bare ``python mrb.py`` works
on any platform without installing anything.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _require(module: str, package: str) -> None:
    try:
        __import__(module)
    except ImportError:
        print(f"Missing dependency: {package}\n"
              f"Install the requirements first:\n\n"
              f"    {sys.executable} -m pip install -r requirements.txt\n")
        raise SystemExit(3)


if __name__ == "__main__":
    _require("PIL", "Pillow")
    _require("UnityPy", "UnityPy")
    from medarot.cli import main

    raise SystemExit(main())
