"""CI-safe tests for barrel-maintenance verbs (winetricks/winecfg/kill/shell/doctor).

The env+argv builders are pure; the CLI spawns through an injected runner, so no
Wine is touched.
"""

from __future__ import annotations

from gest.core.drydock import barrels, maintenance
from gest.core.drydock.model import Barrel
from gest.tui.drydock.cli import CliIO, DrydockEnv, run_cli


# ---- pure builders -----------------------------------------------------
def test_barrel_env():
    b = Barrel(id="o", name="O", runner="wine", arch="win32",
               prefix="/pfx", env={"WINEDEBUG": "-all"})
    assert maintenance.barrel_env(b) == {
        "WINEDEBUG": "-all", "WINEPREFIX": "/pfx", "WINEARCH": "win32"}


def test_argv_builders():
    assert maintenance.winetricks_argv(["dotnet48", "corefonts"]) == \
        ["winetricks", "dotnet48", "corefonts"]
    assert maintenance.winecfg_argv() == ["winecfg"]
    assert maintenance.kill_argv() == ["wineserver", "-k"]
    assert maintenance.shell_argv("/bin/zsh") == ["/bin/zsh"]
    assert maintenance.shell_argv("") == ["bash"]


def test_probe_tools_with_injected_which():
    present = {"wine", "winetricks"}
    probed = maintenance.probe_tools(lambda t: f"/usr/bin/{t}" if t in present else None)
    by_tool = {tool: path for tool, path, _ in probed}
    assert by_tool["wine"] == "/usr/bin/wine"
    assert by_tool["gamescope"] is None
    assert set(by_tool) == set(maintenance.TOOLS)


# ---- CLI ---------------------------------------------------------------
class _H:
    def __init__(self, tmp_path, *, which=lambda t: "/usr/bin/" + t):
        self.out: list[str] = []
        self.err: list[str] = []
        self.spawned: list = []
        self.store = str(tmp_path / "barrels")
        self.env = DrydockEnv(
            io=CliIO(out=self.out.append, err=self.err.append), store_base=self.store,
            tool_spawn=lambda argv, e: self.spawned.append((argv, e)) or 0, which=which)
        barrels.save_barrel(Barrel(id="office", name="Office", runner="wine", arch="win64"),
                            self.store)


def test_winetricks_runs_and_records_verbs(tmp_path):
    h = _H(tmp_path)
    assert run_cli(["winetricks", "office", "dotnet48", "corefonts"], env=h.env) == 0
    argv, envd = h.spawned[0]
    assert argv == ["winetricks", "dotnet48", "corefonts"]
    assert envd["WINEPREFIX"].endswith("/office/prefix")
    # the verbs were recorded back onto the barrel
    barrel = barrels.load_barrel("office", h.store)
    assert "dotnet48" in barrel.verbs and "corefonts" in barrel.verbs


def test_winetricks_needs_a_verb(tmp_path):
    h = _H(tmp_path)
    assert run_cli(["winetricks", "office"], env=h.env) == 2
    assert h.spawned == []


def test_winecfg_and_kill_spawn_with_prefix(tmp_path):
    h = _H(tmp_path)
    assert run_cli(["winecfg", "office"], env=h.env) == 0
    assert run_cli(["kill", "office"], env=h.env) == 0
    assert h.spawned[0][0] == ["winecfg"]
    assert h.spawned[1][0] == ["wineserver", "-k"]
    assert all(e["WINEPREFIX"].endswith("/office/prefix") for _, e in h.spawned)


def test_shell_spawns(tmp_path):
    h = _H(tmp_path)
    assert run_cli(["shell", "office"], env=h.env) == 0
    assert len(h.spawned) == 1  # a shell was launched with the barrel env


def test_verbs_on_unknown_barrel(tmp_path):
    h = _H(tmp_path)
    assert run_cli(["winecfg", "nope"], env=h.env) == 1
    assert h.spawned == []


def test_doctor_reports_missing(tmp_path):
    h = _H(tmp_path, which=lambda t: "/usr/bin/wine" if t == "wine" else None)
    assert run_cli(["doctor"], env=h.env) == 0
    joined = "\n".join(h.out)
    assert "ok  " in joined and "MISS" in joined
    # all tools but wine are missing.
    assert f"{len(maintenance.TOOLS) - 1} tool(s) missing" in joined
