"""Language packs: a directory under ``langs/`` is a language.

Adding one must not require touching any Python. See
``docs/specs/SPEC-004-language-pack.md``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import catalog

CODE_RE = re.compile(r"^[a-z]{2,3}(-[a-z0-9]{2,8})*$")

DEFAULT_MAX_LINE = 46
DEFAULT_LENGTH_FACTOR = 1.25


class LangError(Exception):
    pass


@dataclass
class FontConfig:
    #: TextMeshPro font asset names to append as fallbacks, by name (SPEC-004/R-6).
    fallbacks: list[str] = field(default_factory=list)
    #: Also fill the global "TMP Settings" fallback list.
    global_fallbacks: bool = False
    #: Zero out negative kerning pairs, which overlap Latin letters.
    neutralize_kerning: bool = False
    #: Zero out negative character spacing and glyph narrowing on text components.
    fix_tmp_metrics: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> "FontConfig":
        data = data or {}
        return cls(
            fallbacks=list(data.get("fallbacks", [])),
            global_fallbacks=bool(data.get("global_fallbacks", False)),
            neutralize_kerning=bool(data.get("neutralize_kerning", False)),
            fix_tmp_metrics=bool(data.get("fix_tmp_metrics", True)),
        )


@dataclass
class ValidationConfig:
    extra_chars: str = ""
    max_line: int = DEFAULT_MAX_LINE
    length_factor: float = DEFAULT_LENGTH_FACTOR

    @classmethod
    def from_dict(cls, data: dict) -> "ValidationConfig":
        data = data or {}
        return cls(
            extra_chars=str(data.get("extra_chars", "")),
            max_line=int(data.get("max_line", DEFAULT_MAX_LINE)),
            length_factor=float(data.get("length_factor", DEFAULT_LENGTH_FACTOR)),
        )


@dataclass
class LanguagePack:
    code: str
    name: str
    mod_name: str
    directory: Path
    english_name: str = ""
    font: FontConfig = field(default_factory=FontConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    ascii_fallback: dict = field(default_factory=dict)
    credits: list = field(default_factory=list)
    #: Everything read from lang.json, so unknown keys survive a save (R-5).
    raw: dict = field(default_factory=dict)

    # ----------------------------------------------------------------- io ---
    @classmethod
    def load(cls, directory) -> "LanguagePack":
        directory = Path(directory)
        manifest = directory / "lang.json"
        if not manifest.exists():
            raise LangError(f"{directory}: no lang.json")
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise LangError(f"{manifest}: invalid JSON ({exc})") from exc

        for required in ("code", "name", "mod_name"):
            if not data.get(required):
                raise LangError(f"{manifest}: missing required field {required!r}")

        code = data["code"]
        if not CODE_RE.match(code):
            raise LangError(f"{manifest}: invalid code {code!r} (expected e.g. 'es', 'pt-br')")
        if code != directory.name:
            raise LangError(f"{manifest}: code {code!r} does not match directory {directory.name!r}")

        mod_name = data["mod_name"]
        if Path(mod_name).name != mod_name or mod_name in {"", ".", ".."}:
            raise LangError(f"{manifest}: mod_name {mod_name!r} must be a single directory name")

        return cls(
            code=code,
            name=data["name"],
            mod_name=mod_name,
            directory=directory,
            english_name=data.get("english_name", ""),
            font=FontConfig.from_dict(data.get("font")),
            validation=ValidationConfig.from_dict(data.get("validation")),
            ascii_fallback=dict(data.get("ascii_fallback", {})),
            credits=list(data.get("credits", [])),
            raw=data,
        )

    def save(self) -> Path:
        """Write lang.json back, preserving unknown keys (SPEC-004/R-5)."""
        data = dict(self.raw)
        data.update({
            "code": self.code,
            "name": self.name,
            "english_name": self.english_name,
            "mod_name": self.mod_name,
            "font": {
                "fallbacks": self.font.fallbacks,
                "global_fallbacks": self.font.global_fallbacks,
                "neutralize_kerning": self.font.neutralize_kerning,
                "fix_tmp_metrics": self.font.fix_tmp_metrics,
            },
            "validation": {
                "extra_chars": self.validation.extra_chars,
                "max_line": self.validation.max_line,
                "length_factor": self.validation.length_factor,
            },
            "ascii_fallback": self.ascii_fallback,
            "credits": self.credits,
        })
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / "lang.json"
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        return target

    # -------------------------------------------------------------- layout --
    @property
    def idxres_dir(self) -> Path:
        return self.directory / "idxres"

    @property
    def labels_file(self) -> Path:
        return self.directory / "labels.json"

    @property
    def textures_dir(self) -> Path:
        return self.directory / "textures"

    @property
    def delta_dir(self) -> Path:
        return self.textures_dir / "delta"

    def table_file(self, table: str) -> Path:
        return self.idxres_dir / f"{table}.json"

    def tables(self) -> list[str]:
        if not self.idxres_dir.is_dir():
            return []
        return sorted(p.stem for p in self.idxres_dir.glob("*.json"))

    @property
    def texture_index_file(self) -> Path:
        """Human-facing note of what each translated texture says (optional)."""
        return self.textures_dir / "textures.json"

    def texture_notes(self) -> list[dict]:
        if not self.texture_index_file.exists():
            return []
        doc = json.loads(self.texture_index_file.read_text(encoding="utf-8"))
        return list(doc.get("textures", []))

    def deltas(self) -> dict[str, Path]:
        """Texture name -> overlay path (masks excluded)."""
        if not self.delta_dir.is_dir():
            return {}
        return {p.stem: p for p in sorted(self.delta_dir.rglob("*.png"))
                if not str(p).endswith(".mask.png")}

    # --------------------------------------------------------------- data ---
    def table_catalog(self, table: str) -> catalog.Catalog:
        return catalog.Catalog.load(self.table_file(table), catalog.KIND_IDXRES)

    def label_catalog(self) -> catalog.Catalog:
        return catalog.Catalog.load(self.labels_file, catalog.KIND_LABELS)

    def stats(self) -> dict:
        """Counts for the status display."""
        translated = total = 0
        for table in self.tables():
            done, count = self.table_catalog(table).stats()
            translated += done
            total += count
        labels = self.label_catalog()
        label_done, label_total = labels.stats()
        return {
            "tables": len(self.tables()),
            "text_translated": translated,
            "text_total": total,
            "labels_translated": label_done,
            "labels_total": label_total,
            "textures": len(self.deltas()),
            "texture_notes": len(self.texture_notes()),
        }

    def ascii_table(self):
        """``str.translate`` table for ``--ascii`` (SPEC-006/R-10)."""
        if not self.ascii_fallback:
            return None
        return str.maketrans(self.ascii_fallback)

    def label(self) -> str:
        return f"{self.code} ({self.name})"


def discover(langs_dir) -> list[LanguagePack]:
    """Every readable language pack, sorted by code (SPEC-004/R-1)."""
    langs_dir = Path(langs_dir)
    if not langs_dir.is_dir():
        return []
    packs = []
    for directory in sorted(p for p in langs_dir.iterdir() if p.is_dir()):
        if not (directory / "lang.json").exists():
            continue
        packs.append(LanguagePack.load(directory))
    return packs


def get(langs_dir, code: str) -> LanguagePack:
    directory = Path(langs_dir) / code
    if not (directory / "lang.json").exists():
        available = ", ".join(p.code for p in discover(langs_dir)) or "none"
        raise LangError(f"unknown language {code!r} (available: {available})")
    return LanguagePack.load(directory)


def create(langs_dir, code: str, name: str, *, english_name: str = "",
           mod_name: str = "", template: LanguagePack | None = None) -> LanguagePack:
    """Create a new, empty language pack.

    If ``template`` is given, its keys are copied with empty translations so the
    new language starts with the full list of things to translate.
    """
    if not CODE_RE.match(code):
        raise LangError(f"invalid code {code!r} (expected e.g. 'es', 'fr', 'pt-br')")
    directory = Path(langs_dir) / code
    if (directory / "lang.json").exists():
        raise LangError(f"{code} already exists at {directory}")

    pack = LanguagePack(
        code=code,
        name=name,
        mod_name=mod_name or f"MedarotRB_{code.upper().replace('-', '_')}",
        directory=directory,
        english_name=english_name or name,
        font=FontConfig(neutralize_kerning=True, fix_tmp_metrics=True),
        validation=ValidationConfig(),
    )
    pack.idxres_dir.mkdir(parents=True, exist_ok=True)
    pack.delta_dir.mkdir(parents=True, exist_ok=True)
    pack.save()

    if template is not None:
        for table in template.tables():
            source = template.table_catalog(table)
            blank = catalog.Catalog(kind=catalog.KIND_IDXRES, meta=dict(source.meta))
            blank.entries = [
                {"row": e["row"], "sub": e["sub"], "col": e["col"],
                 "src": e.get("src", ""), "t": ""}
                for e in source.entries
            ]
            blank.save(pack.table_file(table))
        source_labels = template.label_catalog()
        blank_labels = catalog.Catalog(kind=catalog.KIND_LABELS,
                                       meta=dict(source_labels.meta))
        blank_labels.entries = [{"src": e["src"], "t": ""}
                                for e in source_labels.entries if e.get("src")]
        blank_labels.save(pack.labels_file)

        # Which textures have text baked in is the same in every language, so the
        # list comes across with the translations blanked out.
        notes = template.texture_notes()
        if notes:
            blank_notes = [{"texture": item["texture"], "text": "",
                            **({"note": item["note"]} if item.get("note") else {})}
                           for item in notes]
            pack.texture_index_file.write_text(
                json.dumps({"textures": blank_notes}, ensure_ascii=False, indent=1)
                + "\n", encoding="utf-8")

    return pack
