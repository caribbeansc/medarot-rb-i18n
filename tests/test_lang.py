"""SPEC-004 — language pack layout."""

from __future__ import annotations

import json

import pytest

from medarot import lang


def write_pack(root, code: str, **overrides) -> None:
    data = {"code": code, "name": code.upper(), "mod_name": f"Mod_{code}"}
    data.update(overrides)
    directory = root / code
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "lang.json").write_text(json.dumps(data), encoding="utf-8")


def test_r1_discover_only_finds_dirs_with_a_manifest(tmp_path):
    """SPEC-004/R-1."""
    write_pack(tmp_path, "es")
    write_pack(tmp_path, "fr")
    (tmp_path / "notalang").mkdir()
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    assert [p.code for p in lang.discover(tmp_path)] == ["es", "fr"]


def test_r1_discover_on_missing_dir_is_empty(tmp_path):
    assert lang.discover(tmp_path / "nope") == []


@pytest.mark.parametrize("missing", ["code", "name", "mod_name"])
def test_r2_required_fields(tmp_path, missing):
    """SPEC-004/R-2: the message names the file and the field."""
    data = {"code": "es", "name": "Español", "mod_name": "M"}
    del data[missing]
    (tmp_path / "es").mkdir(parents=True)
    (tmp_path / "es" / "lang.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(lang.LangError, match=missing):
        lang.LanguagePack.load(tmp_path / "es")


@pytest.mark.parametrize("code", ["ES", "e", "spanish_latam", "es_MX", "1x", ""])
def test_r3_invalid_codes_are_rejected(tmp_path, code):
    """SPEC-004/R-3."""
    with pytest.raises(lang.LangError):
        lang.create(tmp_path, code, "X")


@pytest.mark.parametrize("code", ["es", "fr", "pt-br", "zh-hans"])
def test_r3_valid_codes_are_accepted(tmp_path, code):
    pack = lang.create(tmp_path, code, "X")
    assert pack.code == code


@pytest.mark.parametrize("mod_name", ["../escape", "a/b", "..", ""])
def test_r3_mod_name_cannot_escape(tmp_path, mod_name):
    """SPEC-004/R-3: mod_name is a single path segment."""
    write_pack(tmp_path, "es", mod_name=mod_name)
    with pytest.raises(lang.LangError, match="mod_name|required"):
        lang.LanguagePack.load(tmp_path / "es")


def test_r3_code_must_match_directory(tmp_path):
    (tmp_path / "es").mkdir(parents=True)
    (tmp_path / "es" / "lang.json").write_text(
        json.dumps({"code": "fr", "name": "Français", "mod_name": "M"}),
        encoding="utf-8")
    with pytest.raises(lang.LangError, match="does not match directory"):
        lang.LanguagePack.load(tmp_path / "es")


def test_r4_documented_defaults(tmp_path):
    """SPEC-004/R-4: every optional field has the documented default."""
    write_pack(tmp_path, "es")
    pack = lang.LanguagePack.load(tmp_path / "es")
    assert pack.font.fallbacks == []
    assert pack.font.global_fallbacks is False
    assert pack.font.neutralize_kerning is False
    assert pack.font.fix_tmp_metrics is True
    assert pack.validation.extra_chars == ""
    assert pack.validation.max_line == lang.DEFAULT_MAX_LINE
    assert pack.validation.length_factor == lang.DEFAULT_LENGTH_FACTOR
    assert pack.ascii_fallback == {}
    assert pack.ascii_table() is None


def test_r5_unknown_keys_survive_a_save(tmp_path):
    """SPEC-004/R-5."""
    write_pack(tmp_path, "es", _future_field={"a": 1})
    pack = lang.LanguagePack.load(tmp_path / "es")
    pack.save()
    data = json.loads((tmp_path / "es" / "lang.json").read_text(encoding="utf-8"))
    assert data["_future_field"] == {"a": 1}


def test_r6_fallbacks_are_names_not_ids(tmp_path):
    """SPEC-004/R-6: fallback fonts are named, so a pack survives another dump."""
    write_pack(tmp_path, "es", font={"fallbacks": ["LiberationSans SDF"]})
    pack = lang.LanguagePack.load(tmp_path / "es")
    assert pack.font.fallbacks == ["LiberationSans SDF"]
    assert all(isinstance(name, str) for name in pack.font.fallbacks)


def test_r8_packs_are_independent(tmp_path):
    """SPEC-004/R-8: two packs can disagree and never read each other."""
    es = lang.create(tmp_path, "es", "Español")
    fr = lang.create(tmp_path, "fr", "Français")
    (es.idxres_dir / "T.json").write_text(json.dumps(
        {"table": "T", "entries": [{"row": "a", "sub": 0, "col": "c",
                                    "src": "s", "t": "uno"}]}), encoding="utf-8")
    (fr.idxres_dir / "T.json").write_text(json.dumps(
        {"table": "T", "entries": [{"row": "a", "sub": 0, "col": "c",
                                    "src": "s", "t": "un"}]}), encoding="utf-8")
    assert es.table_catalog("T").entries[0]["t"] == "uno"
    assert fr.table_catalog("T").entries[0]["t"] == "un"


def test_create_makes_the_layout(tmp_path):
    pack = lang.create(tmp_path, "de", "Deutsch")
    assert (pack.directory / "lang.json").exists()
    assert pack.idxres_dir.is_dir()
    assert pack.delta_dir.is_dir()
    assert pack.mod_name == "MedarotRB_DE"


def test_create_refuses_to_overwrite(tmp_path):
    lang.create(tmp_path, "de", "Deutsch")
    with pytest.raises(lang.LangError, match="already exists"):
        lang.create(tmp_path, "de", "Deutsch")


def test_create_from_template_copies_keys_but_no_translations(tmp_path):
    source = lang.create(tmp_path, "es", "Español")
    (source.idxres_dir / "T.json").write_text(json.dumps({
        "table": "T",
        "entries": [{"row": "a", "sub": 0, "col": "c", "src": "s1", "t": "uno"}],
    }), encoding="utf-8")
    source.labels_file.write_text(json.dumps(
        {"entries": [{"src": "s2", "t": "dos"}]}), encoding="utf-8")
    source.texture_index_file.write_text(json.dumps(
        {"textures": [{"texture": "Card", "text": "CAMBIAR"}]}), encoding="utf-8")

    new = lang.create(tmp_path, "it", "Italiano", template=source)
    entry = new.table_catalog("T").entries[0]
    assert entry["row"] == "a" and entry["src"] == "s1" and entry["t"] == ""
    assert new.label_catalog().entries == [{"src": "s2", "t": ""}]
    assert new.texture_notes() == [{"texture": "Card", "text": ""}]


def test_get_reports_available_languages(tmp_path):
    lang.create(tmp_path, "es", "Español")
    with pytest.raises(lang.LangError, match="available: es"):
        lang.get(tmp_path, "nope")


def test_ascii_table_translates(tmp_path):
    write_pack(tmp_path, "es", ascii_fallback={"á": "a", "¡": ""})
    pack = lang.LanguagePack.load(tmp_path / "es")
    assert "¡Vámonos!".translate(pack.ascii_table()) == "Vamonos!"


def test_stats_counts_everything(tmp_path):
    pack = lang.create(tmp_path, "es", "Español")
    (pack.idxres_dir / "T.json").write_text(json.dumps({
        "table": "T",
        "entries": [{"row": "a", "sub": 0, "col": "c", "src": "s", "t": "uno"},
                    {"row": "b", "sub": 0, "col": "c", "src": "s2", "t": ""}],
    }), encoding="utf-8")
    stats = pack.stats()
    assert stats["text_translated"] == 1 and stats["text_total"] == 2
    assert stats["tables"] == 1
