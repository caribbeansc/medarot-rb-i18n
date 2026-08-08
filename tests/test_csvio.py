"""Spreadsheet round-trip (``mrb csv``)."""

from __future__ import annotations

import csv

import pytest

from medarot import csvio, extract, workspace

from .conftest import JP_HELLO


@pytest.fixture
def space(project_with_romfs, pack):
    extract.refresh_all(project_with_romfs, tables=True, bundles=False, scenes=False)
    space = workspace.Workspace(project=project_with_romfs, pack=pack)
    space.refresh()
    return space


def read_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_export_has_a_bom_and_the_documented_columns(space, tmp_path):
    dest = tmp_path / "x.csv"
    rows = csvio.export(space, dest)
    assert dest.read_bytes().startswith(b"\xef\xbb\xbf"), "Excel needs the BOM"
    assert rows == 3
    assert list(read_rows(dest)[0]) == csvio.COLUMNS


def test_export_carries_the_source_text(space, tmp_path):
    dest = tmp_path / "x.csv"
    csvio.export(space, dest)
    sources = {row["source"] for row in read_rows(dest)}
    assert JP_HELLO in sources


def test_pending_only_skips_finished_rows(space, tmp_path):
    dest = tmp_path / "x.csv"
    total = csvio.export(space, dest)
    pending = csvio.export(space, dest, pending_only=True)
    assert pending < total


def test_import_applies_translations(space, tmp_path):
    dest = tmp_path / "x.csv"
    csvio.export(space, dest)
    rows = read_rows(dest)
    for row in rows:
        row["translation"] = "imported"
    with open(dest, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=csvio.COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    report = csvio.import_csv(space, dest)
    assert report.applied + report.unchanged == len(rows)
    assert all(entry["t"] == "imported"
               for entry in space.table_catalog("Test").entries)


def test_import_reports_unknown_keys(space, tmp_path):
    dest = tmp_path / "x.csv"
    with open(dest, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=csvio.COLUMNS)
        writer.writeheader()
        writer.writerow({"where": "Test", "key": "Ghost|0|0|text|aaaaaaaaaaaa",
                         "translation": "x"})
    report = csvio.import_csv(space, dest)
    assert report.unknown == 1 and report.applied == 0


def test_import_ignores_empty_translations(space, tmp_path):
    dest = tmp_path / "x.csv"
    csvio.export(space, dest)
    report = csvio.import_csv(space, dest)
    # the fixture has two translated rows already; they come back unchanged
    assert report.applied == 0
    assert report.unchanged == 2


def test_import_rejects_a_file_without_the_columns(space, tmp_path):
    dest = tmp_path / "bad.csv"
    dest.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(csvio.CsvError, match="missing column"):
        csvio.import_csv(space, dest)


def test_import_of_a_missing_file_fails(space, tmp_path):
    with pytest.raises(csvio.CsvError, match="not found"):
        csvio.import_csv(space, tmp_path / "nope.csv")


def test_malformed_key_is_rejected(space, tmp_path):
    dest = tmp_path / "bad.csv"
    dest.write_text("where,key,translation\nTest,not-a-key,x\n", encoding="utf-8")
    with pytest.raises(csvio.CsvError, match="malformed key"):
        csvio.import_csv(space, dest)


def test_label_keys_survive_the_round_trip(space, tmp_path):
    from medarot import catalog

    labels = space.label_catalog()
    labels.entries = [catalog.label_entry(JP_HELLO, "")]
    labels.save(space.labels_file)

    dest = tmp_path / "x.csv"
    csvio.export(space, dest)
    rows = [row for row in read_rows(dest) if row["where"] == "labels"]
    assert rows and rows[0]["key"] == catalog.fingerprint(JP_HELLO)

    rows[0]["translation"] = "Hola"
    with open(dest, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=csvio.COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    report = csvio.import_csv(space, dest)
    assert report.applied == 1
    assert space.label_catalog().entries[0]["t"] == "Hola"
