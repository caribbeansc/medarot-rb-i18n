"""Translation catalogs: the on-disk shape of a translation, without the source.

Two kinds, both a JSON object with an ``entries`` list:

*positional*: an IdxRes table cell, addressed by where it lives::

    {"row": "Ok", "sub": 0, "col": "text", "src": "8b1a7f22c0d4", "t": "Aceptar"}

*content-addressed*: a label serialized in a bundle or scene, addressed by the
fingerprint of the original::

    {"src": "3fa9c1e0b7d2", "t": "Turno {0}", "note": "battle HUD"}

The work copies under ``work/`` add a ``jp`` field with the original text so a
human can translate; ``mrb sync`` strips it when promoting into ``langs/``.
See ``docs/specs/SPEC-005-translation-keys.md``.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

FINGERPRINT_LEN = 12

#: Ranges that must never appear in a published catalog (SPEC-005/R-4). Fullwidth
#: forms matter: a cell whose whole content is "？" is still the game's text.
SOURCE_TEXT_RE = re.compile(
    "["
    "　-〿"   # CJK punctuation, ideographic space
    "぀-ゟ"   # hiragana
    "゠-ヿ"   # katakana
    "㐀-䶿"   # CJK unified ideographs extension A
    "一-鿿"   # CJK unified ideographs
    "豈-﫿"   # CJK compatibility ideographs
    "＀-￯"   # halfwidth and fullwidth forms
    "]"
)

#: Field order in written files, so diffs stay small and reviewable.
FIELD_ORDER = ["row", "n", "sub", "col", "src", "jp", "t", "note", "where", "seen"]

KIND_IDXRES = "idxres"
KIND_LABELS = "labels"


class CatalogError(Exception):
    pass


def fingerprint(text: str) -> str:
    """Stable short fingerprint of a source string (SPEC-005/R-1)."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return digest[:FINGERPRINT_LEN]


def has_source_text(value: str) -> bool:
    """True if the string contains Japanese (kana, CJK or CJK punctuation)."""
    return bool(SOURCE_TEXT_RE.search(value))


def cell_key(row: str, sub: int, col: str, n: int = 0) -> tuple:
    """Where one table cell lives.

    ``n`` is the ordinal of the row among the rows sharing ``row``: row keys are
    not unique (SPEC-001/R-6), so without it two different cells would collide.
    It is 0 for the overwhelming majority of cells and omitted from the file then.
    """
    return (row, int(n), int(sub), col)


def entry_key(entry: dict, kind: str):
    """The identity of an entry: where it lives *and* which text it translates.

    A cell can hold different Japanese in different versions of the game: the
    v1.1 update rewrote fifteen of them: and those may need different
    translations. So the fingerprint is part of the key, and a position may appear
    more than once (SPEC-005/R-9).
    """
    if kind == KIND_IDXRES:
        return cell_key(entry["row"], entry["sub"], entry["col"],
                        entry.get("n", 0)) + (entry.get("src", ""),)
    return entry["src"]


def cell_position(entry: dict) -> tuple:
    """The address alone, without the fingerprint."""
    return cell_key(entry["row"], entry["sub"], entry["col"], entry.get("n", 0))


def _ordered(entry: dict) -> dict:
    known = {k: entry[k] for k in FIELD_ORDER if k in entry}
    extra = {k: v for k, v in entry.items() if k not in known}
    return {**known, **extra}


@dataclass
class Catalog:
    """A list of translation entries plus whatever metadata the file carries."""

    kind: str
    path: Path | None = None
    meta: dict = field(default_factory=dict)
    entries: list[dict] = field(default_factory=list)

    # ----------------------------------------------------------------- io ---
    @classmethod
    def load(cls, path, kind: str) -> "Catalog":
        path = Path(path)
        if not path.exists():
            return cls(kind=kind, path=path)
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CatalogError(f"{path}: invalid JSON ({exc})") from exc
        if not isinstance(doc, dict) or not isinstance(doc.get("entries"), list):
            raise CatalogError(f"{path}: expected an object with an 'entries' list")
        meta = {k: v for k, v in doc.items() if k != "entries"}
        return cls(kind=kind, path=path, meta=meta, entries=list(doc["entries"]))

    def save(self, path=None, *, strip_source: bool = False) -> Path:
        """Write the catalog. ``strip_source`` drops the ``jp`` field."""
        target = Path(path or self.path)
        if target is None:
            raise CatalogError("no path to save to")
        entries = []
        for entry in self.entries:
            out = dict(entry)
            if strip_source:
                out.pop("jp", None)
                out.pop("where", None)
                out.pop("seen", None)
            entries.append(_ordered(out))
        doc = {**self.meta, "entries": entries}
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        return target

    # -------------------------------------------------------------- access --
    def index(self) -> dict:
        return {entry_key(e, self.kind): e for e in self.entries}

    def translations(self) -> dict:
        """Key -> translation, for entries that actually have one."""
        return {entry_key(e, self.kind): e["t"]
                for e in self.entries if e.get("t")}

    def by_fingerprint(self) -> dict:
        return {e["src"]: e for e in self.entries if e.get("src")}

    def stats(self) -> tuple[int, int]:
        """``(translated, total)``"""
        return sum(1 for e in self.entries if e.get("t")), len(self.entries)

    def untranslated(self) -> list[dict]:
        return [e for e in self.entries if not e.get("t")]

    # --------------------------------------------------------------- merge --
    def merge_from(self, other: "Catalog") -> int:
        """Copy translations from ``other`` into matching entries.

        Only fills entries that are still empty, so re-extracting can never
        clobber work in progress (SPEC-005/R-7). Returns how many were filled.
        """
        source = other.translations()
        filled = 0
        for entry in self.entries:
            if entry.get("t"):
                continue
            value = source.get(entry_key(entry, self.kind))
            if value:
                entry["t"] = value
                filled += 1
        # carry notes across as well; they are the translator's own comments
        notes = {entry_key(e, self.kind): e.get("note")
                 for e in other.entries if e.get("note")}
        for entry in self.entries:
            note = notes.get(entry_key(entry, self.kind))
            if note and not entry.get("note"):
                entry["note"] = note
        return filled

    def check_collisions(self) -> list[str]:
        """Fingerprint collisions between different source strings (SPEC-005/R-3)."""
        seen: dict[str, str] = {}
        problems = []
        for entry in self.entries:
            src, source_text = entry.get("src"), entry.get("jp")
            if not src or source_text is None:
                continue
            previous = seen.setdefault(src, source_text)
            if previous != source_text:
                problems.append(
                    f"fingerprint {src} is shared by two different source strings"
                )
        return problems

    def check_no_source_text(self) -> list[str]:
        """Published catalogs must not carry source text (SPEC-005/R-4)."""
        problems = []
        for entry in self.entries:
            for field_name in ("t", "note"):
                value = entry.get(field_name)
                if isinstance(value, str) and has_source_text(value):
                    key = entry_key(entry, self.kind)
                    problems.append(f"{key}: {field_name} contains source text")
        return problems


def idxres_entry(row: str, sub: int, col: str, source: str, translation: str = "",
                 *, n: int = 0, with_source: bool = True) -> dict:
    entry = {"row": row}
    if n:
        entry["n"] = int(n)
    entry.update({
        "sub": int(sub),
        "col": col,
        "src": fingerprint(source),
        "t": translation,
    })
    if with_source:
        entry["jp"] = source
    return entry


def label_entry(source: str, translation: str = "", note: str = "",
                *, with_source: bool = True) -> dict:
    entry = {"src": fingerprint(source), "t": translation}
    if with_source:
        entry["jp"] = source
    if note:
        entry["note"] = note
    return entry


def scan_tree_for_source_text(root) -> list[str]:
    """Files under ``root`` that contain Japanese text (SPEC-005/R-4, R-8).

    Binary files are skipped: a PNG delta may legitimately contain any bytes.
    """
    offenders = []
    for path in sorted(Path(root).rglob("*")):
        if not path.is_file() or path.suffix.lower() in {".png", ".ttf", ".otf"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if has_source_text(text):
            offenders.append(str(path))
    return offenders
