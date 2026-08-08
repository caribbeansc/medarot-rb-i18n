"""SPEC-007 — command line interface."""

from __future__ import annotations

import builtins
import json

import pytest

from medarot import cli, config, ui


@pytest.fixture(autouse=True)
def _in_project(monkeypatch, tmp_path, sample_table):
    """Run the CLI against a throwaway project, never the user's own."""
    from medarot.formats import idxres

    romfs = tmp_path / "romfs"
    (romfs / config.IDXRES_DIR).mkdir(parents=True)
    (romfs / config.IDXRES_DIR / "IdxRes_Test.bytes").write_bytes(
        idxres.build(sample_table))
    (romfs / config.BUNDLE_DIR).mkdir(parents=True)

    project = config.Project(root=tmp_path, romfs=romfs, work=tmp_path / "work",
                            build=tmp_path / "build", langs=tmp_path / "langs")
    monkeypatch.setattr(config, "load", lambda root=None: project)
    monkeypatch.setattr(config, "detect_mod_targets", lambda *a, **k: [])
    monkeypatch.setattr(cli.config, "detect_mod_targets", lambda *a, **k: [])
    return project


def test_r1_no_args_without_a_tty_prints_status(monkeypatch, capsys):
    """SPEC-007/R-1: never blocks on input when there is no terminal."""
    monkeypatch.setattr(ui, "is_tty", lambda: False)
    monkeypatch.setattr(builtins, "input",
                        lambda *a: pytest.fail("must not prompt"))
    assert cli.main([]) == cli.EXIT_OK
    assert "translation toolkit" in capsys.readouterr().out


def test_r2_subcommands_never_prompt(monkeypatch, capsys):
    """SPEC-007/R-2: missing information is an error naming the flag."""
    monkeypatch.setattr(ui, "is_tty", lambda: False)
    monkeypatch.setattr(builtins, "input",
                        lambda *a: pytest.fail("must not prompt"))
    assert cli.main(["setup"]) == cli.EXIT_USAGE
    assert "--romfs" in capsys.readouterr().out


def test_r4_no_colour_when_not_a_tty(monkeypatch):
    """SPEC-007/R-4."""
    monkeypatch.setattr(ui, "is_tty", lambda: False)
    monkeypatch.setattr(ui, "_COLOUR", None)
    assert ui.use_colour() is False
    assert ui.paint("x", ui.RED) == "x"


def test_r4_no_color_env_disables_colour(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(ui, "is_tty", lambda: True)
    assert ui.use_colour() is False


def test_r7_exit_code_for_missing_game_files(monkeypatch, capsys):
    """SPEC-007/R-7: 3 means the game files are missing or unusable."""
    monkeypatch.setattr(ui, "is_tty", lambda: False)
    assert cli.main(["setup", "--romfs", "/definitely/not/here"]) == cli.EXIT_NO_GAME
    assert "does not look like" in capsys.readouterr().out


def test_r7_exit_code_for_a_failed_step(monkeypatch, capsys):
    monkeypatch.setattr(ui, "is_tty", lambda: False)
    cli.main(["newlang", "xx", "--name", "Testish"])
    capsys.readouterr()
    assert cli.main(["build", "nope"]) == cli.EXIT_FAILED
    assert "unknown language" in capsys.readouterr().out


def test_r7_success_is_zero(monkeypatch):
    monkeypatch.setattr(ui, "is_tty", lambda: False)
    assert cli.main(["status"]) == cli.EXIT_OK


def test_setup_stores_the_romfs(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(ui, "is_tty", lambda: False)
    romfs = config.load().romfs
    assert cli.main(["setup", "--romfs", str(romfs)]) == cli.EXIT_OK
    stored = json.loads((tmp_path / config.CONFIG_NAME).read_text(encoding="utf-8"))
    assert stored["romfs"] == str(romfs)


def test_full_flow_newlang_extract_build(monkeypatch, capsys):
    """The documented sequence works end to end on a synthetic dump."""
    monkeypatch.setattr(ui, "is_tty", lambda: False)
    assert cli.main(["newlang", "xx", "--name", "Testish"]) == cli.EXIT_OK
    assert cli.main(["extract", "--tables-only"]) == cli.EXIT_OK

    project = config.load()
    work_file = project.work_lang("xx") / "idxres" / "Test.json"
    doc = json.loads(work_file.read_text(encoding="utf-8"))
    doc["entries"][0]["t"] = "Accept"
    work_file.write_text(json.dumps(doc), encoding="utf-8")

    assert cli.main(["sync", "xx"]) == cli.EXIT_OK
    assert cli.main(["validate", "xx"]) == cli.EXIT_OK
    assert cli.main(["build", "xx"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "Mod:" in out

    published = json.loads((project.langs / "xx" / "idxres" / "Test.json")
                           .read_text(encoding="utf-8"))
    assert "jp" not in published["entries"][0]


def test_build_with_nothing_translated_fails(monkeypatch, capsys):
    monkeypatch.setattr(ui, "is_tty", lambda: False)
    cli.main(["newlang", "xx", "--name", "Testish"])
    assert cli.main(["build", "xx"]) == cli.EXIT_FAILED
    assert "nothing was applied" in capsys.readouterr().out


def test_doctor_reports_and_exits_zero(monkeypatch, capsys):
    monkeypatch.setattr(ui, "is_tty", lambda: False)
    cli.main(["newlang", "xx", "--name", "Testish"])
    assert cli.main(["doctor"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "UnityPy" in out and "no source text" in out


def test_doctor_fails_on_source_text_in_a_pack(monkeypatch, capsys):
    """SPEC-005/R-8: doctor is how a contributor checks before a pull request."""
    monkeypatch.setattr(ui, "is_tty", lambda: False)
    cli.main(["newlang", "xx", "--name", "Testish"])
    project = config.load()
    (project.langs / "xx" / "oops.json").write_text("こんにちは", encoding="utf-8")
    assert cli.main(["doctor"]) == cli.EXIT_FAILED
    assert "source text" in capsys.readouterr().out


def test_csv_roundtrip(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(ui, "is_tty", lambda: False)
    cli.main(["newlang", "xx", "--name", "Testish"])
    cli.main(["extract", "--tables-only"])

    out_csv = tmp_path / "x.csv"
    assert cli.main(["csv", "xx", "--out", str(out_csv)]) == cli.EXIT_OK
    text = out_csv.read_text(encoding="utf-8-sig")
    assert "Test|" in text or "Test" in text

    rows = text.splitlines()
    header, first = rows[0], rows[1].split(",")
    assert header.startswith("where,key,source,translation")
    patched = rows[:1] + [f"{first[0]},{first[1]},,imported,"] + rows[2:]
    out_csv.write_text("\n".join(patched), encoding="utf-8-sig")

    assert cli.main(["csv", "xx", "--import", str(out_csv)]) == cli.EXIT_OK
    assert "1 translations imported" in capsys.readouterr().out


def test_install_refuses_without_a_build(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(ui, "is_tty", lambda: False)
    cli.main(["newlang", "xx", "--name", "Testish"])
    assert cli.main(["install", "xx", "--to", str(tmp_path / "mods")]) == cli.EXIT_FAILED


def test_help_lists_every_command(capsys):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["--help"])
    out = capsys.readouterr().out
    for command in ("setup", "prepare", "extract", "sync", "validate", "build",
                    "install", "newlang", "textures", "assets", "csv", "doctor"):
        assert command in out


def test_r3_menu_is_numeric(monkeypatch, capsys):
    """SPEC-007/R-3: choices are typed digits, no raw terminal mode."""
    answers = iter(["9", "1"])
    monkeypatch.setattr(builtins, "input", lambda *a: next(answers))
    choice = ui.menu([("1", "One", ""), ("2", "Two", "")], quit_key=None)
    assert choice == "1"
    assert "Type one of" in capsys.readouterr().out


def test_r5_confirm_yes_flag_skips_the_question(monkeypatch):
    """SPEC-007/R-5."""
    monkeypatch.setattr(builtins, "input",
                        lambda *a: pytest.fail("must not prompt"))
    assert ui.confirm("Delete everything?", assume_yes=True) is True


def test_r9_ctrl_c_at_a_prompt_raises_aborted(monkeypatch):
    """SPEC-007/R-9."""
    def interrupt(*_):
        raise KeyboardInterrupt

    monkeypatch.setattr(builtins, "input", interrupt)
    with pytest.raises(ui.Aborted):
        ui.ask("anything")


def test_r9_aborting_a_command_exits_cleanly(monkeypatch):
    def interrupt(*_):
        raise KeyboardInterrupt

    monkeypatch.setattr(builtins, "input", interrupt)
    monkeypatch.setattr(ui, "is_tty", lambda: True)
    assert cli.main(["setup"]) == cli.EXIT_OK


def test_progress_is_line_based_without_a_tty(monkeypatch, capsys):
    """SPEC-007/R-8."""
    monkeypatch.setattr(ui, "is_tty", lambda: False)
    progress = ui.Progress("things", 2)
    progress.advance("first")
    progress.advance("second")
    progress.done("finished")
    out = capsys.readouterr().out
    assert "\r" not in out
    assert "things: 1/2" in out and "finished" in out


# ------------------------------------------------------- interactive menu ----

def drive(monkeypatch, answers):
    """Run the interactive menu with a canned sequence of keystrokes."""
    typed = iter(answers)
    monkeypatch.setattr(ui, "is_tty", lambda: True)
    monkeypatch.setattr(builtins, "input", lambda *a: next(typed))
    return typed


def test_r1_menu_runs_when_there_is_a_tty(monkeypatch, capsys):
    """SPEC-007/R-1: a terminal gets the menu, not the status dump."""
    drive(monkeypatch, ["0"])
    assert cli.main([]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "Translate" in out and "Build a mod" in out


def test_r6_menu_redraws_the_project_state(monkeypatch, capsys):
    """SPEC-007/R-6: the menu doubles as the status display."""
    cli.main(["newlang", "xx", "--name", "Testish"])
    capsys.readouterr()
    drive(monkeypatch, ["0"])
    cli.main([])
    out = capsys.readouterr().out
    assert "Game files" in out and "xx" in out


def test_menu_can_run_diagnose_and_come_back(monkeypatch, capsys):
    drive(monkeypatch, ["9", "", "0"])     # diagnose, enter at the pause, quit
    assert cli.main([]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "Environment" in out


def test_menu_reports_errors_without_crashing(monkeypatch, capsys):
    """A step that fails must not take the menu down with it."""
    drive(monkeypatch, ["4", "", "0"])     # translate, with no language yet
    assert cli.main([]) == cli.EXIT_OK
    assert "no language packs" in capsys.readouterr().out


def test_menu_translate_submenu_opens(monkeypatch, capsys):
    cli.main(["newlang", "xx", "--name", "Testish"])
    cli.main(["extract", "--tables-only"])
    capsys.readouterr()
    # translate -> validate -> pause -> quit
    drive(monkeypatch, ["4", "5", "", "0"])
    assert cli.main([]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "translations checked" in out


def test_r9_ctrl_c_at_the_menu_quits_cleanly(monkeypatch):
    """SPEC-007/R-9."""
    def interrupt(*_):
        raise KeyboardInterrupt

    monkeypatch.setattr(ui, "is_tty", lambda: True)
    monkeypatch.setattr(builtins, "input", interrupt)
    assert cli.main([]) == cli.EXIT_OK


def test_setup_asks_for_the_path_when_interactive(monkeypatch, capsys):
    project = config.load()
    drive(monkeypatch, [str(project.romfs)])
    assert cli.main(["setup"]) == cli.EXIT_OK
    assert "Game files:" in capsys.readouterr().out


def test_ui_helpers_render_without_a_tty(monkeypatch, capsys):
    monkeypatch.setattr(ui, "is_tty", lambda: False)
    monkeypatch.setattr(ui, "_COLOUR", None)
    ui.banner("Title", "subtitle")
    ui.heading("Heading")
    ui.step("Step")
    ui.detail("detail")
    ui.ok("ok")
    ui.warn("warn")
    ui.fail("fail")
    ui.info("info")
    ui.kv("key", "value", status="ok")
    ui.bullets(["one", "two"])
    ui.table([("a", "1"), ("bb", "22")], headers=["name", "n"])
    out = capsys.readouterr().out
    for expected in ("Title", "Heading", "Step", "detail", "ok", "warn", "fail",
                     "info", "value", "one", "name"):
        assert expected in out


def test_progress_rewrites_a_single_line_on_a_tty(monkeypatch, capsys):
    monkeypatch.setattr(ui, "is_tty", lambda: True)
    progress = ui.Progress("things", 3, every=2)
    for _ in range(3):
        progress.advance()
    progress.done("done")
    out = capsys.readouterr().out
    assert "\r" in out and "things: 3/3" in out


def test_choose_returns_the_item(monkeypatch):
    drive(monkeypatch, ["2"])
    assert ui.choose(["a", "b", "c"]) == "b"
