"""SPEC-006/R-8, R-9 — installing into emulators, and detecting them."""

from __future__ import annotations

import pytest

from medarot import config, install


@pytest.fixture
def built(project_with_romfs, pack):
    from medarot import build

    build.run(project_with_romfs, pack, only=["tables"])
    return project_with_romfs, pack


def test_r8_installs_into_an_explicit_directory(built, tmp_path):
    project, pack = built
    target = tmp_path / "mods" / "contents" / config.TITLE_ID.lower()
    done = install.install(project, pack, target)
    assert len(done) == 1
    assert (target / pack.mod_name / "romfs").is_dir()
    assert done[0].files >= 1


def test_r8_reinstalling_replaces_only_its_own_directory(built, tmp_path):
    project, pack = built
    target = tmp_path / "mods"
    other = target / "SomeoneElsesMod"
    other.mkdir(parents=True)
    (other / "keep.txt").write_text("x", encoding="utf-8")

    install.install(project, pack, target)
    stale = target / pack.mod_name / "romfs" / "stale.bin"
    stale.write_bytes(b"x")
    install.install(project, pack, target)

    assert not stale.exists(), "the mod directory should be replaced"
    assert (other / "keep.txt").exists(), "nothing outside it may be touched"


def test_r8_uninstall_removes_only_the_mod(built, tmp_path):
    project, pack = built
    target = tmp_path / "mods"
    install.install(project, pack, target)
    removed = install.uninstall(project, pack, target)
    assert removed and not (target / pack.mod_name).exists()
    assert target.exists()


def test_install_without_a_build_says_so(project_with_romfs, pack, tmp_path):
    with pytest.raises(install.InstallError, match="mrb build"):
        install.install(project_with_romfs, pack, tmp_path)


def test_plan_reports_the_final_paths(built, tmp_path):
    project, pack = built
    plan = install.plan(project, pack, tmp_path)
    assert plan[0][1] == tmp_path / pack.mod_name


def test_r9_detection_covers_both_layouts(monkeypatch, tmp_path):
    """SPEC-006/R-9: Ryujinx-style lowercase, yuzu-style uppercase."""
    ryujinx = tmp_path / "Ryujinx" / "mods" / "contents"
    yuzu = tmp_path / "yuzu" / "load"
    ryujinx.mkdir(parents=True)
    yuzu.mkdir(parents=True)

    monkeypatch.setattr(config, "_emulator_roots", lambda: [
        ("Ryujinx", ryujinx, "ryujinx"),
        ("yuzu", yuzu, "yuzu"),
        ("Missing", tmp_path / "nope", "yuzu"),
    ])
    found = {t.emulator: t.path for t in config.detect_mod_targets()}
    assert found["Ryujinx"].name == config.TITLE_ID.lower()
    assert found["yuzu"].name == config.TITLE_ID.upper()
    assert "Missing" not in found


def test_r9_real_detection_runs_on_this_platform():
    """It must not raise, whatever platform the tests run on."""
    for target in config.detect_mod_targets():
        assert target.path.name.lower() == config.TITLE_ID.lower()
        assert target.style in {"ryujinx", "yuzu"}


def test_r9_roots_are_platform_specific(monkeypatch):
    import platform

    for system in ("Windows", "Darwin", "Linux"):
        monkeypatch.setattr(platform, "system", lambda system=system: system)
        monkeypatch.setenv("APPDATA", "C:/Users/x/AppData/Roaming")
        roots = config._emulator_roots()
        assert roots, system
        assert all(style in {"ryujinx", "yuzu"} for _, _, style in roots)


def test_no_emulator_found_gives_a_usable_message(built, monkeypatch):
    project, pack = built
    monkeypatch.setattr(config, "_emulator_roots", lambda: [])
    with pytest.raises(install.InstallError, match="--to"):
        install.install(project, pack, None)


# --------------------------------------------------- another title (Kabuto) --

def test_r15_title_id_is_configuration(tmp_path):
    """SPEC-006/R-15: the sister release is a different title, same formats."""
    project = config.Project(root=tmp_path, romfs=None, work=tmp_path / "w",
                             build=tmp_path / "b", langs=tmp_path / "l")
    assert project.title_id == config.TITLE_ID
    project.set_title_id("0100cb6025008000")
    assert project.title_id == "0100CB6025008000"

    reloaded = config.load(tmp_path)
    assert reloaded.title_id == "0100CB6025008000"


@pytest.mark.parametrize("bad", ["0100CB60", "not-hex-at-all!!", "", "0" * 17])
def test_r15_invalid_title_ids_are_rejected(tmp_path, bad):
    from medarot.config import ConfigError

    project = config.Project(root=tmp_path, romfs=None, work=tmp_path / "w",
                             build=tmp_path / "b", langs=tmp_path / "l")
    with pytest.raises(ConfigError, match="title id"):
        project.set_title_id(bad)


def test_r15_detection_follows_the_configured_title(monkeypatch, tmp_path):
    ryujinx = tmp_path / "Ryujinx" / "mods" / "contents"
    ryujinx.mkdir(parents=True)
    monkeypatch.setattr(config, "_emulator_roots",
                        lambda: [("Ryujinx", ryujinx, "ryujinx")])
    found = config.detect_mod_targets("0100CB6025008000")
    assert found[0].path.name == "0100cb6025008000"


def test_r15_packaging_follows_the_configured_title(built, tmp_path):
    from medarot import package

    project, pack = built
    project.title_id = "0100CB6025008000"
    item = package.stage(project, pack, package.ATMOSPHERE)
    assert "0100CB6025008000" in item.romfs.as_posix()


def test_environment_overrides_the_saved_romfs(tmp_path, monkeypatch, fake_romfs):
    """Two dumps on one machine: the environment wins over the stored config."""
    other = tmp_path / "other-romfs"
    (other / config.IDXRES_DIR).mkdir(parents=True)
    (other / config.IDXRES_DIR / "IdxRes_Test.bytes").write_bytes(
        (fake_romfs / config.IDXRES_DIR / "IdxRes_Test.bytes").read_bytes())

    project = config.Project(root=tmp_path, romfs=fake_romfs, work=tmp_path / "w",
                             build=tmp_path / "b", langs=tmp_path / "l")
    project.save()

    monkeypatch.setenv("MEDAROT_ROMFS", str(other))
    monkeypatch.setenv("MEDAROT_TITLE_ID", "0100DE4023982000")
    loaded = config.load(tmp_path)
    assert loaded.romfs == other.resolve()
    assert loaded.title_id == "0100DE4023982000"

    monkeypatch.delenv("MEDAROT_ROMFS")
    monkeypatch.delenv("MEDAROT_TITLE_ID")
    assert config.load(tmp_path).romfs == fake_romfs


def test_work_area_is_per_dump(tmp_path):
    """Two dumps must not share inventories or caches.

    The sister release ships files with the same names and different contents;
    mixing them would build a mod from the wrong game.
    """
    kuwagata = config.Project(root=tmp_path, romfs=None, work=tmp_path / "work",
                              build=tmp_path / "b", langs=tmp_path / "l")
    kabuto = config.Project(root=tmp_path, romfs=None, work=tmp_path / "work",
                            build=tmp_path / "b", langs=tmp_path / "l",
                            title_id="0100DE4023982000")

    assert kuwagata.dump_work != kabuto.dump_work
    for attribute in ("raw_dir", "inventory_dir", "assets_dir", "base_cache"):
        assert getattr(kuwagata, attribute) != getattr(kabuto, attribute)
    assert kuwagata.work_lang("es") != kabuto.work_lang("es")
    assert kabuto.dump_work.name == "0100de4023982000"


def write_boot_config(romfs, guid: str) -> None:
    path = romfs / config.BOOT_CONFIG
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"gfx-threading-mode=4\nbuild-guid={guid}\n", encoding="utf-8")


def test_release_is_detected_from_the_dump(tmp_path, fake_romfs):
    """SPEC-006/R-16: the tool works out which dump you have, so you need not.

    Without the update the two releases ship a byte-identical romfs bar four
    files, so nothing but Unity's build id can tell them apart.
    """
    guid = "44c30c35db8f47518de97e8d199abae8"     # Kabuto, base game
    write_boot_config(fake_romfs, guid)

    assert config.build_guid(fake_romfs) == guid
    assert config.detect_release(fake_romfs) == ("0100DE4023982000",
                                                 "Kabuto Ver., base game")

    project = config.Project(root=tmp_path, romfs=None, work=tmp_path / "w",
                             build=tmp_path / "b", langs=tmp_path / "l")
    assert project.set_romfs(fake_romfs) == "Kabuto Ver., base game"
    assert project.title_id == "0100DE4023982000"


def test_every_known_build_maps_to_a_release(tmp_path, fake_romfs):
    """All four known dumps: two releases, each with and without the update."""
    for guid, (title_id, name) in config.BUILD_GUIDS.items():
        write_boot_config(fake_romfs, guid)
        assert config.detect_release(fake_romfs) == (title_id, name)
    assert len(config.BUILD_GUIDS) == 4
    assert len({t for t, _ in config.BUILD_GUIDS.values()}) == 2


def test_base_and_updated_dumps_have_different_fingerprints(tmp_path, fake_romfs):
    """The base game and the update share a title id; the cache must not."""
    project = config.Project(root=tmp_path, romfs=fake_romfs, work=tmp_path / "w",
                             build=tmp_path / "b", langs=tmp_path / "l")
    write_boot_config(fake_romfs, "9a229dcba8c1484eaf260e0f76dd1938")
    base = project.dump_fingerprint()
    write_boot_config(fake_romfs, "5f910fe43b4b45758b7b1e36af48fea4")
    assert project.dump_fingerprint() != base


def test_unrecognised_dump_keeps_the_configured_title(tmp_path, fake_romfs):
    project = config.Project(root=tmp_path, romfs=None, work=tmp_path / "w",
                             build=tmp_path / "b", langs=tmp_path / "l")
    assert config.detect_release(fake_romfs) is None
    assert project.set_romfs(fake_romfs) is None
    assert project.title_id == config.TITLE_ID


def test_release_names(tmp_path):
    assert config.release_name("0100cb6024ff8000") == "Kuwagata Ver."
    assert config.release_name("0100DE4023982000") == "Kabuto Ver."
    assert "unknown" in config.release_name("0000000000000000")
