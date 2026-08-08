"""SPEC-008: translation validator."""

from __future__ import annotations

import json

import pytest

from medarot import catalog, extract, lang, validate, workspace

from .conftest import JP_HELLO, JP_LONG


def report_for(pack, workspace_=None):
    return validate.run(pack, workspace_)


def set_entries(pack, entries):
    cat = catalog.Catalog(kind=catalog.KIND_IDXRES, meta={"table": "Test"})
    cat.entries = entries
    cat.save(pack.table_file("Test"))
    return lang.LanguagePack.load(pack.directory)


def test_r1_errors_fail_warnings_do_not(pack):
    pack = set_entries(pack, [{"row": "a", "sub": 0, "col": "text",
                               "src": "x", "t": JP_HELLO}])
    report = report_for(pack)
    assert report.errors and not report.ok()

    pack = set_entries(pack, [{"row": "a", "sub": 0, "col": "text",
                               "src": "x", "t": "fine"}])
    assert report_for(pack).ok()


def test_r2_findings_are_one_greppable_line(pack):
    pack = set_entries(pack, [{"row": "a", "sub": 0, "col": "text",
                               "src": "x", "t": JP_HELLO}])
    line = report_for(pack).errors[0].line()
    assert "\n" not in line
    assert pack.code in line and "Test" in line and "a/0/text" in line


def test_r3_source_dependent_checks_are_skipped_with_a_notice(pack):
    pack = set_entries(pack, [{"row": "a", "sub": 0, "col": "text",
                               "src": "x", "t": "Something {0}"}])
    report = report_for(pack)
    assert report.skipped_checks
    assert not report.errors            # placeholder check could not run


def test_r3_charset_check_always_runs(pack):
    pack = set_entries(pack, [{"row": "a", "sub": 0, "col": "text",
                               "src": "x", "t": "emoji 🎮"}])
    report = report_for(pack)
    assert any("not in this language's charset" in f.message for f in report.errors)


def test_r4_tag_contents_are_ignored_by_the_charset_check(pack):
    pack = set_entries(pack, [{"row": "a", "sub": 0, "col": "text",
                               "src": "x", "t": "<color=#AABBCC>Fuego</color>"}])
    assert not report_for(pack).errors


def test_placeholders_must_match(pack, project_with_romfs, monkeypatch):
    space = _workspace_with_source(project_with_romfs, pack, "Hola {0} y {1}")
    pack = set_entries(pack, [{"row": "Ok", "sub": 0, "col": "text",
                               "src": catalog.fingerprint(JP_HELLO),
                               "t": "Hola {0}"}])
    report = validate.run(pack, space)
    assert any("placeholders differ" in f.message for f in report.errors)


def test_markup_must_match(pack, project_with_romfs):
    space = _workspace_with_source(project_with_romfs, pack, "x")
    pack = set_entries(pack, [{"row": "Ok", "sub": 0, "col": "text",
                               "src": catalog.fingerprint(JP_HELLO),
                               "t": "<b>bold</b>"}])
    report = validate.run(pack, space)
    assert any("markup differs" in f.message for f in report.errors)


def test_stale_key_is_an_error(pack, project_with_romfs):
    """SPEC-005/R-5 seen from the validator: the game's text moved on."""
    # the dump now holds "different text" where this key used to hold JP_HELLO
    space = _workspace_with_source(project_with_romfs, pack, "different text")
    pack = set_entries(pack, [{"row": "Ok", "sub": 0, "col": "text",
                               "src": catalog.fingerprint(JP_HELLO), "t": "ok"}])
    report = validate.run(pack, space)
    assert any("stale" in f.message for f in report.errors)


def test_unknown_fingerprint_cannot_be_judged_stale(pack, project_with_romfs):
    """A key this dump knows nothing about is not reported as stale."""
    space = _workspace_with_source(project_with_romfs, pack, JP_LONG)
    pack = set_entries(pack, [{"row": "Ok", "sub": 0, "col": "text",
                               "src": "000000000000", "t": "whatever"}])
    report = validate.run(pack, space)
    assert not any("stale" in f.message for f in report.errors)


def test_r5_length_budget_is_a_warning(pack, project_with_romfs):
    space = _workspace_with_source(project_with_romfs, pack, JP_HELLO)
    pack = set_entries(pack, [{
        "row": "Ok", "sub": 0, "col": "text",
        "src": catalog.fingerprint(JP_HELLO),
        "t": "una traduccion mucho mas larga de lo que caben cinco kana",
    }])
    report = validate.run(pack, space)
    assert report.warnings and not report.errors
    assert report.ok() and not report.ok(strict=True)


def test_r6_strict_promotes_warnings(pack, project_with_romfs):
    space = _workspace_with_source(project_with_romfs, pack, JP_HELLO)
    pack = set_entries(pack, [{
        "row": "Ok", "sub": 0, "col": "text",
        "src": catalog.fingerprint(JP_HELLO),
        "t": "x" * 200,
    }])
    report = validate.run(pack, space)
    assert not report.ok(strict=True)


def test_r7_validator_writes_nothing(pack, tmp_path):
    pack = set_entries(pack, [{"row": "a", "sub": 0, "col": "text",
                               "src": "x", "t": "fine"}])
    before = {p: p.read_bytes() for p in pack.directory.rglob("*") if p.is_file()}
    report_for(pack)
    after = {p: p.read_bytes() for p in pack.directory.rglob("*") if p.is_file()}
    assert before == after


def test_empty_translations_are_counted_not_reported(pack):
    pack = set_entries(pack, [{"row": "a", "sub": 0, "col": "text",
                               "src": "x", "t": ""}])
    report = report_for(pack)
    assert report.empty == 1 and report.checked == 0 and not report.findings


def test_source_text_in_a_pack_file_is_an_error(pack):
    (pack.directory / "notes.md").write_text(JP_HELLO, encoding="utf-8")
    report = report_for(pack)
    assert any("must not be published" in f.message for f in report.errors)


def test_allowed_control_characters(pack):
    pack = set_entries(pack, [{"row": "a", "sub": 0, "col": "text",
                               "src": "x", "t": "line one\r\nline two\ttabbed"}])
    assert not report_for(pack).errors


def _workspace_with_source(project, pack, source_text: str):
    """A workspace whose source map has JP_HELLO -> the given source text."""
    extract.write_inventory(project, "tables", {
        "Test": [{"row": "Ok", "sub": 0, "col": "text", "text": JP_HELLO}]})
    space = workspace.Workspace(project=project, pack=pack)
    space.idxres_dir.mkdir(parents=True, exist_ok=True)
    (space.idxres_dir / "Test.json").write_text(json.dumps({
        "table": "Test",
        "entries": [{"row": "Ok", "sub": 0, "col": "text",
                     "src": catalog.fingerprint(JP_HELLO),
                     "jp": source_text, "t": ""}],
    }), encoding="utf-8")
    return space
