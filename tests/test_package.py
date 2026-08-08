"""SPEC-006/R-11 … R-14 — packaging for emulators and for Atmosphère."""

from __future__ import annotations

import zipfile

import pytest

from medarot import build, config, package


@pytest.fixture
def built(project_with_romfs, pack):
    build.run(project_with_romfs, pack, only=["tables"])
    return project_with_romfs, pack


def test_r11_both_layouts_come_from_one_build(built):
    """SPEC-006/R-11: the two romfs trees are byte-identical."""
    project, pack = built
    packages = package.build_all(project, pack)
    assert {p.format for p in packages} == set(package.FORMATS)

    contents = []
    for item in packages:
        files = {p.relative_to(item.romfs): p.read_bytes()
                 for p in sorted(item.romfs.rglob("*")) if p.is_file()}
        assert files, item.format
        contents.append(files)
    assert contents[0] == contents[1]


def test_r12_atmosphere_layout(built):
    """SPEC-006/R-12: uppercase title id, no mod name, under /atmosphere."""
    project, pack = built
    item = package.stage(project, pack, package.ATMOSPHERE)
    relative = item.romfs.relative_to(item.root).as_posix()
    assert relative == f"atmosphere/contents/{config.TITLE_ID.upper()}/romfs"
    assert pack.mod_name not in relative


def test_r12_emulator_layout(built):
    """SPEC-006/R-12: named mod directory, nothing above it."""
    project, pack = built
    item = package.stage(project, pack, package.EMULATOR)
    relative = item.romfs.relative_to(item.root).as_posix()
    assert relative == f"{pack.mod_name}/romfs"
    assert "atmosphere" not in relative


def test_r13_zip_paths_are_relative_to_the_layout_root(built):
    """SPEC-006/R-13: unzipping at the SD root puts files in the right place."""
    project, pack = built
    item = package.stage(project, pack, package.ATMOSPHERE)
    archive = package.archive(item)
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
    assert names
    prefix = f"atmosphere/contents/{config.TITLE_ID.upper()}/romfs/"
    assert all(name.startswith(prefix) for name in names), names[:3]
    assert not any(name.startswith("/") or ".." in name for name in names)


def test_r13_emulator_zip_starts_at_the_mod_name(built):
    project, pack = built
    item = package.stage(project, pack, package.EMULATOR)
    with zipfile.ZipFile(package.archive(item)) as zf:
        assert all(name.startswith(f"{pack.mod_name}/") for name in zf.namelist())


def test_r14_sd_install_touches_only_its_own_tree(built, tmp_path):
    """SPEC-006/R-14."""
    project, pack = built
    sd = tmp_path / "sd"
    (sd / "Nintendo").mkdir(parents=True)
    (sd / "atmosphere" / "contents" / "0100000000001000").mkdir(parents=True)
    (sd / "boot.dat").write_bytes(b"x")

    result = package.install_to_sd(project, pack, sd)
    assert result.files >= 1
    assert (sd / "boot.dat").exists()
    assert (sd / "Nintendo").exists()
    assert (sd / "atmosphere" / "contents" / "0100000000001000").exists()
    assert (sd / "atmosphere" / "contents" / config.TITLE_ID.upper()
            / "romfs" / "Data").is_dir()


def test_r14_sd_install_replaces_a_previous_one(built, tmp_path):
    project, pack = built
    sd = tmp_path / "sd"
    sd.mkdir()
    package.install_to_sd(project, pack, sd)
    stale = (sd / "atmosphere" / "contents" / config.TITLE_ID.upper() / "romfs"
             / "stale.bin")
    stale.write_bytes(b"x")
    package.install_to_sd(project, pack, sd)
    assert not stale.exists()


def test_r14_sd_must_exist(built, tmp_path):
    project, pack = built
    with pytest.raises(package.PackageError, match="SD card"):
        package.install_to_sd(project, pack, tmp_path / "not-mounted")


def test_packaging_without_a_build_fails(project_with_romfs, pack):
    with pytest.raises(package.PackageError, match="mrb build"):
        package.stage(project_with_romfs, pack, package.EMULATOR)


def test_unknown_format_is_rejected(built):
    project, pack = built
    with pytest.raises(package.PackageError, match="unknown format"):
        package.stage(project, pack, "3ds")


def test_restaging_replaces_the_previous_output(built):
    project, pack = built
    item = package.stage(project, pack, package.EMULATOR)
    stray = item.root / "stray.txt"
    stray.write_text("x", encoding="utf-8")
    package.stage(project, pack, package.EMULATOR)
    assert not stray.exists()


def test_where_explains_what_to_do(built):
    project, pack = built
    for item in package.build_all(project, pack):
        assert item.where()
