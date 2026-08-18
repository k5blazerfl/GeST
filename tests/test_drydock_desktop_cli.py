"""CI-safe tests for Drydock's Customs integration (synthesize + harvest) and CLI."""

from __future__ import annotations

from typing import NamedTuple

from gest.core.customs import identity_store
from gest.core.customs.desktop import DesktopEntry
from gest.core.drydock import barrels, desktop
from gest.core.drydock.model import RUNNER_WINE, Barrel, Program
from gest.tui.drydock.cli import CliIO, DrydockEnv, run_cli


# ---- desktop synthesis -------------------------------------------------
def test_desktop_id_and_open_argv():
    assert desktop.desktop_id("office", "excel") == "drydock-office-excel"
    assert desktop.open_argv("office", "excel") == ["drydock-run", "office", "excel"]


def test_desktop_entry_synthesis_and_round_trip():
    barrel = Barrel(id="office", name="Office", runner=RUNNER_WINE)
    program = Program(id="excel", name="Excel", exe="C:/office/excel.exe",
                      category="Application", wm_class="excel.exe")
    entry = desktop.desktop_entry(barrel, program)
    assert entry.exec == "drydock-run office excel"
    assert entry.icon == "drydock-office-excel"
    assert entry.startup_wm_class == "excel.exe"
    assert "application/x-ms-dos-executable" in entry.mime_types
    assert entry.extra["X-Drydock-Barrel"] == "office"
    # renders + parses back through Customs
    back = DesktopEntry.parse(entry.render())
    assert back.exec == entry.exec and back.startup_wm_class == "excel.exe"


def test_game_category_and_wm_class_default():
    barrel = Barrel(id="g", name="G", runner=RUNNER_WINE)
    program = Program(id="doom", name="Doom", exe="/pfx/drive_c/doom/DOOM.exe", category="Game")
    entry = desktop.desktop_entry(barrel, program)
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
    prog = desktop.program_from_harvested(entries[0], barrels.slug(entries[0].name))
    assert prog.name in {"Excel", "Notepad"}


def test_harvest_missing_dir_is_empty():
    assert desktop.harvest_dir("/nonexistent/wine/apps") == []


def test_local_exe_path_windows_and_unix():
    barrel = Barrel(id="b", name="B", runner=RUNNER_WINE, prefix="/pfx")
    win = Program(id="e", name="E", exe="C:\\office\\excel.exe")
    assert desktop.local_exe_path(barrel, win) == "/pfx/drive_c/office/excel.exe"
    # a unix path (harvested Exec) is used as-is; no prefix → windows path untouched.
    assert desktop.local_exe_path(barrel, Program(id="u", name="U", exe="/p/a.exe")) == "/p/a.exe"
    noprefix = Barrel(id="b", name="B", runner=RUNNER_WINE)
    assert desktop.local_exe_path(noprefix, win) == "C:\\office\\excel.exe"
    assert desktop.local_exe_path(barrel, Program(id="x", name="X", exe="")) == ""


def test_default_wm_class_prefers_explicit_then_stem():
    assert desktop.default_wm_class(Program(id="e", name="E", exe="a.exe",
                                            wm_class="Excel.exe")) == "Excel.exe"
    assert desktop.default_wm_class(Program(id="d", name="D",
                                            exe="C:/g/DOOM.exe")) == "DOOM"


# ---- CLI ---------------------------------------------------------------
class DEnv(NamedTuple):
    env: DrydockEnv
    out: list
    err: list
    launched: list
    calls: list  # recorded env.run_argv invocations (host tools)
    identity_path: str


def _env(tmp_path) -> DEnv:
    out: list[str] = []
    err: list[str] = []
    launched: list = []
    calls: list = []
    io = CliIO(out=out.append, err=err.append)

    def launch_fn(barrel, program):
        launched.append((barrel, program))
        return 0

    def run_argv(argv):
        calls.append(argv)
        return 0

    identity_path = str(tmp_path / "identity.json")
    env = DrydockEnv(io=io, store_base=str(tmp_path / "barrels"),
                     applications_dir=str(tmp_path / "apps"),
                     wine_apps_dir=str(tmp_path / "wine"), launch_fn=launch_fn,
                     run_argv=run_argv, identity_path=identity_path,
                     icon_theme_dir=str(tmp_path / "icons"))
    return DEnv(env, out, err, launched, calls, identity_path)


def _tools(calls) -> list[str]:
    return [argv[0] for argv in calls if argv]


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
    barrel = barrels.load_barrel("office", str(tmp_path / "barrels"))
    assert barrel.program("excel").graphics.gamescope is True


def test_cli_scan_adopts_wine_apps(tmp_path):
    g = _env(tmp_path)
    run_cli(["create", "Office", "--runner", "wine"], env=g.env)
    winedir = tmp_path / "wine"
    winedir.mkdir()
    (winedir / "Word.desktop").write_text(
        "[Desktop Entry]\nName=Word\nExec=wine /p/word.exe\n")
    assert run_cli(["scan", "office"], env=g.env) == 0
    barrel = barrels.load_barrel("office", str(tmp_path / "barrels"))
    assert barrel.program("word") is not None
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


def test_cli_rm_removes_barrel_and_launchers(tmp_path):
    g = _env(tmp_path)
    run_cli(["create", "Office", "--runner", "wine"], env=g.env)
    run_cli(["register", "office", "/p/x.exe", "--name", "X"], env=g.env)
    assert run_cli(["rm", "office"], env=g.env) == 0
    assert barrels.list_barrels(str(tmp_path / "barrels")) == []
    assert not (tmp_path / "apps" / "drydock-office-x.desktop").exists()


# ---- Customs spine wiring (icon + identity + MIME) ---------------------
def test_cli_register_wires_identity_map(tmp_path):
    g = _env(tmp_path)
    run_cli(["create", "Office", "--runner", "wine"], env=g.env)
    run_cli(["register", "office", "/p/excel.exe", "--name", "Excel"], env=g.env)
    # the window's WM_CLASS resolves back to the synthesized launcher.
    identity = identity_store.load(g.identity_path)
    assert identity.resolve("excel") == "drydock-office-excel"


def test_cli_register_invokes_icon_and_mime_tools(tmp_path):
    g = _env(tmp_path)
    run_cli(["create", "Office", "--runner", "wine"], env=g.env)
    run_cli(["register", "office", "/p/excel.exe", "--name", "Excel"], env=g.env)
    tools = _tools(g.calls)
    # icon extraction (wrestool→icotool), MIME default, and a DB refresh all ran.
    assert "wrestool" in tools and "icotool" in tools
    assert "xdg-mime" in tools and "update-desktop-database" in tools
    xdg = next(c for c in g.calls if c[0] == "xdg-mime")
    assert xdg[:3] == ["xdg-mime", "default", "drydock-office-excel.desktop"]


def test_cli_scan_wires_each_and_refreshes_db_once(tmp_path):
    g = _env(tmp_path)
    run_cli(["create", "Office", "--runner", "wine"], env=g.env)
    winedir = tmp_path / "wine"
    winedir.mkdir()
    (winedir / "Word.desktop").write_text("[Desktop Entry]\nName=Word\nExec=wine /p/word.exe\n")
    (winedir / "Excel.desktop").write_text("[Desktop Entry]\nName=Excel\nExec=wine /p/excel.exe\n")
    assert run_cli(["scan", "office"], env=g.env) == 0
    identity = identity_store.load(g.identity_path)
    assert identity.resolve("word") == "drydock-office-word"
    assert identity.resolve("excel") == "drydock-office-excel"
    # the expensive DB refresh happens once for the whole batch, not per app.
    assert _tools(g.calls).count("update-desktop-database") == 1


def test_cli_rm_unregisters_identity(tmp_path):
    g = _env(tmp_path)
    run_cli(["create", "Office", "--runner", "wine"], env=g.env)
    run_cli(["register", "office", "/p/excel.exe", "--name", "Excel"], env=g.env)
    assert identity_store.load(g.identity_path).resolve("excel") is not None
    run_cli(["rm", "office"], env=g.env)
    assert identity_store.load(g.identity_path).resolve("excel") is None
