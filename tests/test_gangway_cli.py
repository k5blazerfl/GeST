"""CI-safe tests for Gangway's launch orchestration, creds argv, and the CLI —
all with injected spawn / credential-store / IO, so no FreeRDP, keychain, or bus."""

from __future__ import annotations

from typing import NamedTuple

from gest.core.rdp import creds, launcher, run, store
from gest.core.rdp.model import RdpProfile
from gest.tui.gangway.cli import CliIO, GangwayEnv, run_cli


# ---- creds argv --------------------------------------------------------
def test_creds_argv_builders():
    attrs = {"service": "gangway", "host": "pc", "user": "bob"}
    assert creds.store_argv(attrs, "My Label")[:3] == ["secret-tool", "store", "--label=My Label"]
    assert "host" in creds.store_argv(attrs, "L") and "pc" in creds.store_argv(attrs, "L")
    assert creds.lookup_argv(attrs)[:2] == ["secret-tool", "lookup"]
    assert creds.clear_argv(attrs)[:2] == ["secret-tool", "clear"]


# ---- launch orchestration ----------------------------------------------
def test_launch_feeds_password_over_stdin():
    captured = {}

    def spawn(argv, stdin):
        captured["argv"], captured["stdin"] = argv, stdin
        return 0

    profile = RdpProfile(name="x", host="h", username="u")
    rc = run.launch(profile, share_path="/home/u",
                    fetch_password=lambda attrs: "sekret", spawn=spawn)
    assert rc == 0
    assert captured["stdin"] == b"sekret\n"
    assert "/from-stdin" in captured["argv"]
    assert "/v:h:3389" in captured["argv"]


def test_launch_without_password_has_no_stdin_or_from_stdin():
    captured = {}

    def spawn(argv, stdin):
        captured["argv"], captured["stdin"] = argv, stdin
        return 3

    rc = run.launch(RdpProfile(name="x", host="h"),
                    fetch_password=lambda attrs: None, spawn=spawn)
    assert rc == 3
    assert captured["stdin"] is None
    assert "/from-stdin" not in captured["argv"]


# ---- CLI ---------------------------------------------------------------
class GEnv(NamedTuple):
    env: GangwayEnv
    out: list
    err: list
    launched: list
    stored: list
    calls: list  # recorded env.run_argv invocations (host tools)
    identity_path: str


def _env(tmp_path, password="pw") -> GEnv:
    out: list[str] = []
    err: list[str] = []
    launched: list = []
    stored: list = []
    calls: list = []
    io = CliIO(out=out.append, err=err.append, ask_password=lambda prompt: password)

    def launch_fn(profile, share_path=None):
        launched.append((profile, share_path))
        return 0

    def cred_store(attributes, label, pw):
        stored.append((attributes, label, pw))
        return True

    identity_path = str(tmp_path / "identity.json")
    env = GangwayEnv(io=io, store_base=str(tmp_path / "cfg"),
                     applications_dir=str(tmp_path / "apps"),
                     launch_fn=launch_fn, cred_store=cred_store,
                     run_argv=lambda argv: calls.append(argv) or 0,
                     identity_path=identity_path)
    return GEnv(env, out, err, launched, stored, calls, identity_path)


def test_add_list_show(tmp_path):
    g = _env(tmp_path)
    assert run_cli(["add", "work", "--host", "pc.corp", "--user", "bob"], env=g.env) == 0
    g.out.clear()
    assert run_cli(["list"], env=g.env) == 0
    assert g.out == ["work"]
    g.out.clear()
    assert run_cli(["show", "work"], env=g.env) == 0
    joined = "\n".join(g.out)
    assert "pc.corp:3389" in joined and "bob" in joined
    assert "pw" not in joined  # never shows the password


def test_add_rejects_invalid(tmp_path):
    g = _env(tmp_path)
    rc = run_cli(["add", "x", "--host", "h", "--port", "99999"], env=g.env)
    assert rc == 2 and g.err


def test_set_password_stores_via_keychain(tmp_path):
    g = _env(tmp_path, password="hunter2")
    run_cli(["add", "work", "--host", "pc", "--user", "bob"], env=g.env)
    assert run_cli(["set-password", "work"], env=g.env) == 0
    assert len(g.stored) == 1
    attrs, label, pw = g.stored[0]
    assert attrs == {"service": "gangway", "host": "pc", "port": "3389", "user": "bob"}
    assert label == "Gangway: work" and pw == "hunter2"


def test_install_writes_launcher(tmp_path):
    g = _env(tmp_path)
    run_cli(["add", "work", "--host", "pc"], env=g.env)
    assert run_cli(["install", "work"], env=g.env) == 0
    desktop = tmp_path / "apps" / f"{launcher.desktop_id('work')}.desktop"
    assert desktop.exists()
    assert "gangway-open work" in desktop.read_text()


def test_open_invokes_launch(tmp_path):
    g = _env(tmp_path)
    run_cli(["add", "work", "--host", "pc"], env=g.env)
    assert run_cli(["open", "work"], env=g.env) == 0
    assert len(g.launched) == 1
    profile, share = g.launched[0]
    assert profile.host == "pc" and share is not None  # drive_redirect on by default


def test_rm_removes_profile_and_launcher(tmp_path):
    g = _env(tmp_path)
    run_cli(["add", "work", "--host", "pc"], env=g.env)
    run_cli(["install", "work"], env=g.env)
    assert run_cli(["rm", "work"], env=g.env) == 0
    assert store.list_profiles(g.env.store_base) == []
    assert not (tmp_path / "apps" / f"{launcher.desktop_id('work')}.desktop").exists()


def test_open_unknown_profile(tmp_path):
    g = _env(tmp_path)
    assert run_cli(["open", "nope"], env=g.env) == 1
    assert g.err


def test_open_dry_run_prints_command_without_launching(tmp_path):
    g = _env(tmp_path)
    run_cli(["add", "work", "--host", "pc.corp", "--user", "bob"], env=g.env)
    g.out.clear()
    assert run_cli(["open", "work", "--dry-run"], env=g.env) == 0
    printed = "\n".join(g.out)
    assert "sdl-freerdp" in printed and "/v:pc.corp:3389" in printed
    assert g.launched == []  # nothing launched
    assert "/from-stdin" not in printed  # dry run fetches no password


def test_open_file_dry_run(tmp_path):
    g = _env(tmp_path)
    assert run_cli(["open-file", "rdp://host.example:3391", "--dry-run"], env=g.env) == 0
    assert any("/v:host.example:3391" in line for line in g.out)
    assert g.launched == []


# ---- .rdp / rdp:// handler ---------------------------------------------
def test_open_file_launches_rdp_file_adhoc(tmp_path):
    g = _env(tmp_path)
    rdp = tmp_path / "server.rdp"
    rdp.write_text("full address:s:box.corp:3390\nusername:s:alice\n")
    assert run_cli(["open-file", str(rdp)], env=g.env) == 0
    assert len(g.launched) == 1
    profile, _ = g.launched[0]
    assert profile.host == "box.corp" and profile.port == 3390 and profile.username == "alice"
    assert profile.name == "server"  # the file stem — no saved profile needed


def test_open_file_launches_rdp_uri(tmp_path):
    g = _env(tmp_path)
    assert run_cli(["open-file", "rdp://bob@host.example:3391"], env=g.env) == 0
    profile, _ = g.launched[0]
    assert profile.host == "host.example" and profile.port == 3391 and profile.username == "bob"


def test_open_file_missing_file_errors(tmp_path):
    g = _env(tmp_path)
    assert run_cli(["open-file", str(tmp_path / "nope.rdp")], env=g.env) == 1
    assert g.err and not g.launched


def test_register_handler_installs_and_sets_default(tmp_path):
    g = _env(tmp_path)
    assert run_cli(["register-handler"], env=g.env) == 0
    handler = tmp_path / "apps" / f"{launcher.HANDLER_DESKTOP_ID}.desktop"
    assert handler.exists()
    assert "gangway-rdp-open %u" in handler.read_text()
    tools = [c[0] for c in g.calls if c]
    assert "xdg-mime" in tools and "update-desktop-database" in tools
    xdg = next(c for c in g.calls if c[0] == "xdg-mime")
    assert xdg[:3] == ["xdg-mime", "default", f"{launcher.HANDLER_DESKTOP_ID}.desktop"]
    assert "application/x-rdp" in xdg and "x-scheme-handler/rdp" in xdg


def test_register_handler_maps_freerdp_identity(tmp_path):
    from gest.core.customs import identity_store
    g = _env(tmp_path)
    run_cli(["register-handler"], env=g.env)
    identity = identity_store.load(g.identity_path)
    # any FreeRDP window (sdl-freerdp / freerdp / org.freerdp.client) resolves to
    # the handler's stable identity — not per-profile (RAIL is Phase 5).
    assert identity.resolve("sdl-freerdp") == launcher.HANDLER_DESKTOP_ID
    assert identity.resolve("FreeRDP") == launcher.HANDLER_DESKTOP_ID
    assert identity.resolve("org.freerdp.client") == launcher.HANDLER_DESKTOP_ID


def test_unregister_handler_removes(tmp_path):
    from gest.core.customs import identity_store
    g = _env(tmp_path)
    run_cli(["register-handler"], env=g.env)
    assert run_cli(["unregister-handler"], env=g.env) == 0
    assert not (tmp_path / "apps" / f"{launcher.HANDLER_DESKTOP_ID}.desktop").exists()
    assert identity_store.load(g.identity_path).resolve("sdl-freerdp") is None


# ---- import / export .rdp ----------------------------------------------
def test_import_saves_profile(tmp_path):
    g = _env(tmp_path)
    rdp = tmp_path / "work.rdp"
    rdp.write_text("full address:s:pc.corp:3390\nusername:s:bob\ndomain:s:CORP\n")
    assert run_cli(["import", str(rdp)], env=g.env) == 0
    saved = store.load_profile("work", g.env.store_base)  # name from the file stem
    assert saved is not None
    assert saved.host == "pc.corp" and saved.port == 3390 and saved.username == "bob"


def test_import_name_override(tmp_path):
    g = _env(tmp_path)
    rdp = tmp_path / "x.rdp"
    rdp.write_text("full address:s:h\n")
    assert run_cli(["import", str(rdp), "--name", "My Box"], env=g.env) == 0
    assert store.load_profile("My Box", g.env.store_base) is not None


def test_import_missing_file(tmp_path):
    g = _env(tmp_path)
    assert run_cli(["import", str(tmp_path / "nope.rdp")], env=g.env) == 1
    assert g.err


def test_export_to_file(tmp_path):
    g = _env(tmp_path)
    run_cli(["add", "work", "--host", "pc.corp", "--user", "bob"], env=g.env)
    out = tmp_path / "work.rdp"
    assert run_cli(["export", "work", "-o", str(out)], env=g.env) == 0
    text = out.read_text()
    assert "full address:s:pc.corp" in text and "username:s:bob" in text


def test_export_to_stdout(tmp_path):
    g = _env(tmp_path)
    run_cli(["add", "work", "--host", "pc.corp"], env=g.env)
    g.out.clear()
    assert run_cli(["export", "work"], env=g.env) == 0
    assert any("full address:s:pc.corp" in line for line in g.out)


def test_export_unknown_profile(tmp_path):
    g = _env(tmp_path)
    assert run_cli(["export", "nope"], env=g.env) == 1
    assert g.err


def test_import_export_round_trip(tmp_path):
    g = _env(tmp_path)
    run_cli(["add", "work", "--host", "pc.corp", "--user", "bob",
             "--domain", "CORP", "--quality", "lan"], env=g.env)
    out = tmp_path / "work.rdp"
    run_cli(["export", "work", "-o", str(out)], env=g.env)
    run_cli(["import", str(out), "--name", "copy"], env=g.env)
    original = store.load_profile("work", g.env.store_base)
    copy = store.load_profile("copy", g.env.store_base)
    assert (copy.host, copy.username, copy.domain, copy.quality) == \
           (original.host, original.username, original.domain, original.quality)
