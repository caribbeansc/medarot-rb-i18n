"""Build steps. Each one reads a language pack and writes into the mod tree.

Every step follows the same two rules (SPEC-006/R-1, R-4):

* read from the mod tree if the file is already there, else from the prepared
  cache, else from the pristine romfs — so no step can undo another;
* verify what it wrote by reading it back, and fail rather than ship a broken
  bundle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..config import BUNDLE_DIR, DATA_DIR, IDXRES_DIR, Project


@dataclass
class StepResult:
    name: str
    applied: int = 0
    skipped: int = 0
    files: int = 0
    notes: list[str] = field(default_factory=list)

    def note(self, text: str) -> None:
        self.notes.append(text)

    def summary(self) -> str:
        parts = [f"{self.applied} applied"]
        if self.skipped:
            parts.append(f"{self.skipped} skipped")
        if self.files:
            parts.append(f"{self.files} files")
        return ", ".join(parts)


def bundle_rel(name: str) -> str:
    return f"{BUNDLE_DIR}/{name}"


def scene_rel(name: str) -> str:
    return f"{DATA_DIR}/{name}"


def table_rel(name: str) -> str:
    return f"{IDXRES_DIR}/IdxRes_{name}.bytes"


def source_for(project: Project, out_root: Path, relative: str) -> Path:
    """Where to read ``relative`` from, honouring SPEC-006/R-1 and R-4."""
    bases = [out_root]
    if project.use_base_cache:
        bases.append(project.base_cache)
    for base in bases:
        candidate = Path(base) / relative
        if candidate.exists():
            return candidate
    return project.require_romfs() / relative


def apply_ascii(text: str, table) -> str:
    """Degrade a translation to ASCII when ``--ascii`` is in force."""
    return text.translate(table) if table else text
