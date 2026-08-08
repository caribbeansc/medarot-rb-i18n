"""Check a translation before it reaches the game.

Implements ``docs/specs/SPEC-008-validator.md``. Never writes anything.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from . import catalog
from .lang import LanguagePack

TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")
PLACEHOLDER_RE = re.compile(r"\{[0-9]+\}")

ERROR = "error"
WARNING = "warning"
INFO = "info"


@dataclass
class Finding:
    level: str
    lang: str
    where: str
    key: str
    message: str

    def line(self) -> str:
        return f"{self.level.upper():7} {self.lang}  {self.where}  {self.key}  {self.message}"


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    checked: int = 0
    empty: int = 0
    skipped_checks: list[str] = field(default_factory=list)

    def add(self, *args) -> None:
        self.findings.append(Finding(*args))

    def of(self, level: str) -> list[Finding]:
        return [f for f in self.findings if f.level == level]

    @property
    def errors(self) -> list[Finding]:
        return self.of(ERROR)

    @property
    def warnings(self) -> list[Finding]:
        return self.of(WARNING)

    def ok(self, *, strict: bool = False) -> bool:
        if self.errors:
            return False
        return not (strict and self.warnings)


#: Whitespace controls the game's own strings use, so a translation may too.
ALLOWED_CONTROLS = "\n\r\t"


def _allowed(char: str, extra: str) -> bool:
    if char in ALLOWED_CONTROLS or char in extra:
        return True
    if 0x20 <= ord(char) < 0x7F:
        return True
    category = unicodedata.category(char)
    return category.startswith(("L", "N", "P", "S")) and ord(char) < 0x250


def looks_like_a_character_table(source: str) -> bool:
    """True for the entries that list characters rather than say anything.

    The game keeps a font's repertoire and TextMeshPro's line-breaking rules in
    ordinary text fields. They contain Japanese, so they look translatable, and
    "translating" them by dropping the kana breaks line wrapping in the whole
    game. They give themselves away: long, no spaces, almost every character
    distinct.
    """
    stripped = source.replace("\n", "").replace("\ufeff", "")
    if len(stripped) < 25 or " " in stripped:
        return False
    return len(set(stripped)) / len(stripped) > 0.85


def check_translation(report: Report, lang: str, where: str, key: str,
                      translation: str, source: str | None,
                      config, *, src_hash: str = "") -> None:
    plain = TAG_RE.sub("", translation)

    if catalog.has_source_text(translation):
        report.add(ERROR, lang, where, key,
                   f"still contains source text: {translation[:60]!r}")

    # Some entries are not text at all: a font's character repertoire, TMP's
    # line-breaking tables, a developer's note. The right thing to do with those
    # is copy them, so an untouched copy is never a charset error (SPEC-008/R-8).
    if translation != source:
        for char in plain:
            if not _allowed(char, config.extra_chars):
                report.add(ERROR, lang, where, key,
                           f"character {char!r} (U+{ord(char):04X}) is not in this "
                           f"language's charset: {translation[:60]!r}")
                break

    if source is None:
        return

    if src_hash and catalog.fingerprint(source) != src_hash:
        report.add(ERROR, lang, where, key,
                   "the game's text changed since this was translated (stale key)")

    if sorted(PLACEHOLDER_RE.findall(source)) != sorted(PLACEHOLDER_RE.findall(translation)):
        report.add(ERROR, lang, where, key,
                   f"placeholders differ: {PLACEHOLDER_RE.findall(source)} vs "
                   f"{PLACEHOLDER_RE.findall(translation)}")

    if sorted(TAG_RE.findall(source)) != sorted(TAG_RE.findall(translation)):
        report.add(ERROR, lang, where, key,
                   f"markup differs: {TAG_RE.findall(source)} vs "
                   f"{TAG_RE.findall(translation)}")

    cjk_len = len(TAG_RE.sub("", source).replace("\n", ""))
    latin_len = len(plain.replace("\n", ""))
    budget = max(config.length_factor * 2 * cjk_len, cjk_len + 12)
    if latin_len > budget:
        report.add(WARNING, lang, where, key,
                   f"may overflow: {cjk_len} source chars -> {latin_len} chars")

    if looks_like_a_character_table(source) and translation != source:
        report.add(WARNING, lang, where, key,
                   "the original looks like a character repertoire or a line-breaking "
                   "table, not prose. The engine reads it; leave it untranslated.")

    if "\n" in source:
        for line in plain.split("\n"):
            if len(line) > config.max_line:
                report.add(WARNING, lang, where, key,
                           f"line of {len(line)} chars (> {config.max_line}): "
                           f"{line[:50]!r}")
                break


def run(pack: LanguagePack, workspace=None) -> Report:
    """Validate every translation in ``pack``.

    ``workspace`` supplies the source text; without it the checks that need it are
    skipped with a notice (SPEC-008/R-3).
    """
    report = Report()
    sources = workspace.source_map() if workspace is not None else None
    if sources is None:
        report.skipped_checks.append(
            "placeholders, markup, length and staleness need the source text: "
            "run 'mrb extract' first")

    def source_of(entry):
        if sources is None:
            return None
        return sources.get(entry.get("src", ""))

    for table in pack.tables():
        cat = pack.table_catalog(table)
        for entry in cat.entries:
            key = f"{entry['row']}/{entry['sub']}/{entry['col']}"
            if not entry.get("t"):
                report.empty += 1
                continue
            report.checked += 1
            check_translation(report, pack.code, table, key, entry["t"],
                              source_of(entry), pack.validation,
                              src_hash=entry.get("src", ""))

    labels = pack.label_catalog()
    for entry in labels.entries:
        if not entry.get("t"):
            report.empty += 1
            continue
        report.checked += 1
        check_translation(report, pack.code, "labels", entry.get("src", "?"),
                          entry["t"], source_of(entry), pack.validation,
                          src_hash=entry.get("src", ""))

    leftovers = catalog.scan_tree_for_source_text(pack.directory)
    for path in leftovers:
        report.add(ERROR, pack.code, "pack", path,
                   "file contains source text — it must not be published "
                   "(SPEC-005/R-4)")

    return report
