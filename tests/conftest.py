"""Shared fixtures.

Nothing here reads the real game. Tests that need it are marked ``game`` and skip
themselves when no dump is configured, so ``pytest`` passes on a clean checkout.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from medarot import config as mrb_config, lang  # noqa: E402
from medarot.formats import idxres  # noqa: E402

#: Japanese strings used as stand-ins for the game's text. Short, generic words
#: that carry no content from the game.
JP_HELLO = "こんにちは"
JP_MENU = "メニュー"
JP_LONG = "これはテストのための文章です"


def pytest_configure(config):
    config.addinivalue_line("markers", "game: needs a real romfs (set MEDAROT_ROMFS)")


@pytest.fixture
def sample_table() -> idxres.Table:
    """A table exercising every column type, including empty and non-ASCII."""
    table = idxres.Table(
        bytes_path="Assets/StreamingAssets/IdxResData/IdxRes_Test.bytes",
        xlsx_path="Assets/CnvData/IdxResData/IdxRes_Test.xlsx",
        sheet="Test",
        start_cell="B3",
        columns=[
            idxres.Column(idxres.TYPE_INT, "id"),
            idxres.Column(idxres.TYPE_FLOAT, "scale"),
            idxres.Column(idxres.TYPE_BOOL, "enabled"),
            idxres.Column(idxres.TYPE_STRING, "text"),
            idxres.Column(idxres.TYPE_INT_ARRAY, "ids"),
            idxres.Column(idxres.TYPE_FLOAT_ARRAY, "offsets"),
            idxres.Column(idxres.TYPE_BLOB, "colour"),
        ],
    )
    table.rows = [
        idxres.Row("Ok", [[1, 0.5, True, JP_HELLO, [1, 2, 3], [0.25], {"hex": "ff0000ff"}]]),
        idxres.Row("Empty", [[-1, 0.0, False, "", [], [], {"hex": "00000000"}]]),
        # the same key twice, with two sub-rows on the second one (SPEC-001/R-6)
        idxres.Row("Dup", [[2, 1.0, True, JP_MENU, [7], [1.0, 2.0], {"hex": "0a0b0c0d"}]]),
        idxres.Row("Dup", [
            [3, 2.0, False, JP_LONG, [8, 9], [3.0], {"hex": "01020304"}],
            [4, 3.0, True, "ASCII only", [], [], {"hex": "05060708"}],
        ]),
    ]
    return table


@pytest.fixture
def project(tmp_path) -> mrb_config.Project:
    """An empty project rooted in a temporary directory."""
    return mrb_config.Project(
        root=tmp_path,
        romfs=None,
        work=tmp_path / "work",
        build=tmp_path / "build",
        langs=tmp_path / "langs",
    )


@pytest.fixture
def fake_romfs(tmp_path, sample_table) -> Path:
    """A romfs with one real IdxRes table and nothing else."""
    romfs = tmp_path / "romfs"
    tables = romfs / mrb_config.IDXRES_DIR
    tables.mkdir(parents=True)
    (tables / "IdxRes_Test.bytes").write_bytes(idxres.build(sample_table))
    (romfs / mrb_config.BUNDLE_DIR).mkdir(parents=True)
    return romfs


@pytest.fixture
def project_with_romfs(project, fake_romfs) -> mrb_config.Project:
    project.romfs = fake_romfs
    return project


@pytest.fixture
def pack(project) -> lang.LanguagePack:
    """A minimal language pack that translates the sample table."""
    created = lang.create(project.langs, "xx", "Testish")
    created.idxres_dir.mkdir(parents=True, exist_ok=True)
    (created.idxres_dir / "Test.json").write_text(json.dumps({
        "table": "Test",
        "entries": [
            {"row": "Ok", "sub": 0, "col": "text",
             "src": _fingerprint(JP_HELLO), "t": "Accept"},
            {"row": "Dup", "sub": 0, "col": "text",
             "src": _fingerprint(JP_MENU), "t": "Menu"},
        ],
    }, indent=1), encoding="utf-8")
    return lang.LanguagePack.load(created.directory)


def _fingerprint(text: str) -> str:
    from medarot.catalog import fingerprint

    return fingerprint(text)


@pytest.fixture
def real_project():
    """The user's own project, skipped when no dump is available."""
    real = mrb_config.load(REPO)
    if not real.has_romfs():
        pytest.skip("no romfs configured (set MEDAROT_ROMFS or run mrb setup)")
    return real
