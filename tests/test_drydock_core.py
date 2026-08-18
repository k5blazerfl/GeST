"""CI-safe tests for the Drydock core: model, launch pipeline, store, prereqs."""

from __future__ import annotations

from gest.core.drydock import barrels, launch, prereq
from gest.core.drydock.model import (
    RUNNER_PROTON,
    RUNNER_WINE,
    Barrel,
    GraphicsProfile,
    Program,
)


def _wine_barrel(**over) -> Barrel:
    base = dict(id="office", name="Office", runner=RUNNER_WINE, arch="win32",
                prefix="/prefix", dxvk=True)
    base.update(over)
    b = Barrel(**base)
    b.programs.append(Program(id="excel", name="Excel", exe="C:/office/excel.exe",
                              args=["/x"], wm_class="excel.exe"))
    return b


def _proton_barrel(**over) -> Barrel:
    base = dict(id="game", name="Game", runner=RUNNER_PROTON,
                runner_version="GE-Proton9-27", prefix="/gpfx")
    base.update(over)
    return Barrel(**base)


# ---- model -------------------------------------------------------------
def test_barrel_round_trip():
    b = _wine_barrel()
    b.programs[0].graphics = GraphicsProfile(gamescope=True, fsr=True, fps_cap=60)
    back = Barrel.from_dict(b.to_dict())
    assert back == b


def test_barrel_is_valid_and_program_lookup():
    b = _wine_barrel()
    assert b.is_valid()
    assert not Barrel(id="x", name="x", runner="nope").is_valid()
    assert not Barrel(id="x", name="x", runner=RUNNER_WINE, arch="win128").is_valid()
    assert b.program("excel").name == "Excel"
    assert b.program("nope") is None


def test_graphics_from_dict_ignores_unknown_keys():
    g = GraphicsProfile.from_dict({"gamescope": True, "unknown": 5})
    assert g.gamescope is True


# ---- launch env --------------------------------------------------------
def test_env_wine():
    b = _wine_barrel()
    b.programs[0].graphics = GraphicsProfile(dxvk_hud="fps", fps_cap=120, esync=True, fsync=False)
    env = launch.build_env(b, b.programs[0])
    assert env["WINEPREFIX"] == "/prefix"
    assert env["WINEARCH"] == "win32"
    assert env["WINEESYNC"] == "1" and env["WINEFSYNC"] == "0"
    assert env["DXVK_HUD"] == "fps"
    assert env["DXVK_FRAME_RATE"] == "120" and env["VKD3D_FRAME_RATE"] == "120"
    assert "GAMEID" not in env  # wine, not proton


def test_env_proton():
    b = _proton_barrel()
    p = Program(id="mygame", name="G", exe="game.exe")
    env = launch.build_env(b, p)
    assert env["GAMEID"] == "mygame" and env["STORE"] == "none"
    assert env["PROTONPATH"] == "GE-Proton9-27"
    assert env["WINEPREFIX"] == "/gpfx"
    assert "WINEARCH" not in env  # umu/Proton manages it


def test_mangohud_env_only_without_gamescope():
    b = _wine_barrel()
    p = b.programs[0]
    p.graphics = GraphicsProfile(mangohud=True, gamescope=False)
    assert launch.build_env(b, p).get("MANGOHUD") == "1"
    p.graphics = GraphicsProfile(mangohud=True, gamescope=True)
    assert "MANGOHUD" not in launch.build_env(b, p)  # it's --mangoapp instead


# ---- launch argv -------------------------------------------------------
def test_argv_plain_wine_and_proton():
    b = _wine_barrel()
    assert launch.build_argv(b, b.programs[0]) == ["wine", "C:/office/excel.exe", "/x"]
    pb = _proton_barrel()
    p = Program(id="g", name="G", exe="game.exe")
    assert launch.build_argv(pb, p) == ["umu-run", "game.exe"]


def test_argv_gamescope_wrap_order_and_flags():
    b = _wine_barrel()
    p = b.programs[0]
    p.graphics = GraphicsProfile(gamescope=True, gamescope_width=2560, gamescope_height=1440,
                                 fsr=True, hdr=True, mangohud=True, gamemode=True)
    argv = launch.build_argv(b, p)
    # gamemoderun outermost, then gamescope … --, then the runner
    assert argv[0] == "gamemoderun"
    assert argv[1] == "gamescope"
    assert "-W" in argv and "2560" in argv and "-H" in argv and "1440" in argv
    assert "-f" in argv
    assert argv[argv.index("-F") + 1] == "fsr"
    assert "--hdr-enabled" in argv
    assert "--mangoapp" in argv
    dash = argv.index("--")
    assert argv[dash + 1] == "wine"  # runner comes after gamescope's --


def test_launch_calls_spawn_with_argv_and_env():
    b = _wine_barrel()
    captured = {}

    def spawn(argv, env):
        captured["argv"], captured["env"] = argv, env
        return 0

    assert launch.launch(b, b.programs[0], spawn=spawn) == 0
    assert captured["argv"][0] == "wine"
    assert captured["env"]["WINEPREFIX"] == "/prefix"


# ---- store -------------------------------------------------------------
def test_store_round_trip_and_default_prefix(tmp_path):
    b = Barrel(id="office", name="Office", runner=RUNNER_WINE)  # no prefix
    path = barrels.save_barrel(b, base=str(tmp_path))
    assert path.exists()
    # save filled in the default prefix under the barrel dir
    assert b.prefix == str(barrels.default_prefix("office", str(tmp_path)))
    assert barrels.list_barrels(base=str(tmp_path)) == ["office"]
    assert barrels.load_barrel("office", base=str(tmp_path)) == b
    assert barrels.delete_barrel("office", base=str(tmp_path)) is True
    assert barrels.list_barrels(base=str(tmp_path)) == []


def test_slug_and_unsafe_id():
    assert barrels.slug("My Office!") == "my-office"
    assert barrels.slug("") == "barrel"
    for bad in ("../x", "A/B", "Up.Case"):
        try:
            barrels.barrel_dir(bad, base="/tmp")
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {bad!r}")


# ---- prereqs -----------------------------------------------------------
def test_prereqs_proton_needs_umu_from_guru():
    b = _proton_barrel()
    reqs = prereq.requirements(b)
    atoms = {r.atom: r for r in reqs}
    assert "games-util/umu-launcher" in atoms
    assert atoms["games-util/umu-launcher"].from_guru is True
    assert "media-libs/vulkan-loader" in atoms
    assert prereq.needs_guru(b) is True


def test_prereqs_wine_multilib_and_toggles():
    b = _wine_barrel(arch="win32", dxvk=True, vkd3d=True)
    reqs = {r.atom: r for r in prereq.requirements(b)}
    assert "abi_x86_32" in reqs["app-emulation/wine-vanilla"].use
    assert "app-emulation/dxvk" in reqs and "app-emulation/vkd3d-proton" in reqs
    assert not prereq.needs_guru(b)

    b64 = _wine_barrel(arch="win64", dxvk=False, vkd3d=False)
    reqs64 = {r.atom: r for r in prereq.requirements(b64)}
    assert reqs64["app-emulation/wine-vanilla"].use == []  # no multilib for win64


def test_prereqs_game_mode_tools():
    b = _wine_barrel()
    b.programs[0].graphics = GraphicsProfile(gamescope=True, gamemode=True, mangohud=True)
    atoms = {r.atom: r for r in prereq.requirements(b)}
    assert "gui-wm/gamescope" in atoms
    assert "games-util/gamemode" in atoms
    assert "mangoapp" in atoms["games-util/mangohud"].use
