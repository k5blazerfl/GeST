"""CI-safe tests for Drydock's Customs integration (synthesize + harvest) and CLI."""

from __future__ import annotations

from typing import NamedTuple

from gest.core.customs.desktop import DesktopEntry
from gest.core.drydock import bottles, desktop
from gest.core.drydock.model import RUNNER_WINE, Bottle, Program
from gest.tui.drydock.cli import CliIO, DrydockEnv, run_cli


# ---- desktop synthesis -------------------------------------------------
def test_desktop_id_and_open_argv():
    assert desktop.desktop_id("office", "excel") == "drydock-office-excel"
    assert desktop.open_argv("office", "excel") == ["drydock-run", "office", "excel"]


def test_desktop_entry_synthesis_and_round_trip():
    bottle = Bottle(id="office", name="Office", runner=RUNNER_WINE)
    program = Program(id="excel", name="Excel", exe="C:/office/excel.exe",
                      category="Application", wm_class="excel.exe")
    entry = desktop.desktop_entry(bottle, program)
    assert entry.exec == "drydock-run office excel"
    assert entry.icon == "drydock-office-excel"
    assert entry.startup_wm_class == "excel.exe"
    assert "application/x-ms-dos-executable" in entry.mime_types
    assert entry.extra["X-Drydock-Bottle"] == "office"
    # renders + parses back through Customs
    back = DesktopEntry.parse(entry.render())
    assert back.exec == entry.exec and back.startup_wm_class == "excel.exe"


def test_game_category_and_wm_class_default():
    bottle = Bottle(id="g", name="G", runner=RUNNER_WINE)
    program = Program(id="doom", name="Doom", exe="/pfx/drive_c/doom/DOOM.exe", category="Game")
    entry = desktop.desktop_entry(bottle, program)
    assert entry.categories == ["Game"]
    assert entry.startup_wm_class == "DOOM"  # derived from the exe basename


# ---- harvesting wine launchers -----------------------------------------
def test_extract_exe_from_wine_execs():
    def exe(line):
        return desktop.program_from_harvested(
            DesktopEntry(name="x", exec=line), "x").exe
    assert exe("env WINEPREFIX=/p wine /pfx/drive_c/app.exe %U") == "/pfx/drive_c/app.exe"
    assert exe("wine start /unix /path/to/game.exe") == "/path/to/game.exe"
    assert exe("env FOO=1 wine notepad") == "notepad"  # no .exe → token after wine


def test_harvest_dir(tmp_path):
    winedir = tmp_path / "wine" / "Programs"
    winedir.mkdir(parents=True)
    (winedir / "Excel.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Excel\n"
        "Exec=env WINEPREFIX=/p wine /p/drive_c/office/excel.exe\nIcon=excel\n")
    (winedir / "Notepad.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Notepad\nExec=wine notepad.exe\n")
    entries = desktop.harvest_dir(str(tmp_path / "wine"))
    assert {e.name for e in entries} == {"Excel", "Notepad"}
    prog = desktop.program_from_harvested(entries[0], bottles.slug(entries[0].name))
    assert prog.name in {"Excel", "Notepad"}


def test_harvest_missing_dir_is_empty():
    assert desktop.harvest_dir("/nonexistent/wine/apps") == []


# ---- CLI ---------------------------------------------------------------
class DEnv(NamedTuple):
    env: DrydockEnv
    out: list
    err: list
    launched: list


def _env(tmp_path) -> DEnv:
    out: list[str] = []
    err: list[str] = []
    launched: list = []
    io = CliIO(out=out.append, err=err.append)

    def launch_fn(bottle, program):
        launched.append((bottle, program))
        return 0

    env = DrydockEnv(io=io, store_base=str(tmp_path / "bottles"),
                     applications_dir=str(tmp_path / "apps"),
                     wine_apps_dir=str(tmp_path / "wine"), launch_fn=launch_fn)
    return DEnv(env, out, err, launched)


def test_cli_create_list_show(tmp_path):
    g = _env(tmp_path)
    assert run_cli(["create", "Office", "--runner", "wine", "--arch", "win32"], env=g.env) == 0
    g.out.clear()
    assert run_cli(["list"], env=g.env) == 0
    assert g.out == ["office"]
    g.out.clear()
    assert run_cli(["show", "office"], env=g.env) == 0
    assert any("arch=win32" in line for line in g.out)


def test_cli_register_writes_launcher(tmp_path):
    g = _env(tmp_path)
    run_cli(["create", "Office", "--runner", "wine"], env=g.env)
    assert run_cli(["register", "office", "/p/excel.exe", "--name", "Excel",
                    "--gamescope", "--fsr"], env=g.env) == 0
    launcher = tmp_path / "apps" / "drydock-office-excel.desktop"
    assert launcher.exists()
    assert "drydock-run office excel" in launcher.read_text()
    bottle = bottles.load_bottle("office", str(tmp_path / "bottles"))
    assert bottle.program("excel").graphics.gamescope is True


def test_cli_scan_adopts_wine_apps(tmp_path):
    g = _env(tmp_path)
    run_cli(["create", "Office", "--runner", "wine"], env=g.env)
    winedir = tmp_path / "wine"
    winedir.mkdir()
    (winedir / "Word.desktop").write_text(
        "[Desktop Entry]\nName=Word\nExec=wine /p/word.exe\n")
    assert run_cli(["scan", "office"], env=g.env) == 0
    bottle = bottles.load_bottle("office", str(tmp_path / "bottles"))
    assert bottle.program("word") is not None
    assert (tmp_path / "apps" / "drydock-office-word.desktop").exists()


def test_cli_prereqs_proton_mentions_guru(tmp_path):
    g = _env(tmp_path)
    run_cli(["create", "Game", "--runner", "proton"], env=g.env)
    assert run_cli(["prereqs", "game"], env=g.env) == 0
    joined = "\n".join(g.out)
    assert "umu-launcher" in joined and "GURU" in joined


def test_cli_run_invokes_launch(tmp_path):
    g = _env(tmp_path)
    run_cli(["create", "Office", "--runner", "wine"], env=g.env)
    run_cli(["register", "office", "/p/excel.exe", "--name", "Excel"], env=g.env)
    assert run_cli(["run", "office", "excel"], env=g.env) == 0
    assert len(g.launched) == 1 and g.launched[0][1].id == "excel"


def test_cli_run_unknown(tmp_path):
    g = _env(tmp_path)
    run_cli(["create", "Office", "--runner", "wine"], env=g.env)
    assert run_cli(["run", "office", "nope"], env=g.env) == 1
    assert g.err


def test_cli_rm_removes_bottle_and_launchers(tmp_path):
    g = _env(tmp_path)
    run_cli(["create", "Office", "--runner", "wine"], env=g.env)
    run_cli(["register", "office", "/p/x.exe", "--name", "X"], env=g.env)
    assert run_cli(["rm", "office"], env=g.env) == 0
    assert bottles.list_bottles(str(tmp_path / "bottles")) == []
    assert not (tmp_path / "apps" / "drydock-office-x.desktop").exists()
