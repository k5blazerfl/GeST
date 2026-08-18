"""CI-safe tests for the Gangway RDP core (model, .rdp file, commands, store,
launcher). Launching a real session is a host-only concern; here everything is
pure data + argv/file building."""

from __future__ import annotations

from gest.core.customs.desktop import DesktopEntry
from gest.core.rdp import commands, launcher, rdpfile, store
from gest.core.rdp.model import RdpProfile


def _profile(**over) -> RdpProfile:
    base = dict(name="Work PC", host="pc.corp", port=3390, username="bob", domain="CORP",
                fullscreen=True, width=2560, height=1440, multimon=True,
                dynamic_resolution=True, gateway_host="gw.corp", quality="lan",
                clipboard=True, drive_redirect=True, audio_output=True, microphone=True,
                printers=True, nla=True)
    base.update(over)
    return RdpProfile(**base)


# ---- model -------------------------------------------------------------
def test_credential_attributes():
    p = _profile()
    attrs = p.credential_attributes()
    assert attrs == {"service": "gangway", "host": "pc.corp", "port": "3390",
                     "user": "bob", "domain": "CORP"}
    # identity-only fields; a password lookup ignores redirection prefs
    assert "quality" not in attrs and "clipboard" not in attrs


def test_is_valid():
    assert _profile().is_valid()
    assert not RdpProfile(name="x", host="").is_valid()
    assert not RdpProfile(name="x", host="h", quality="ultra").is_valid()
    assert not RdpProfile(name="x", host="h", port=0).is_valid()


# ---- .rdp file ---------------------------------------------------------
def test_rdp_round_trip_preserves_all_fields():
    p = _profile()
    back = rdpfile.parse(rdpfile.render(p), p.name)
    assert back == p


def test_default_port_omitted_from_address():
    p = _profile(port=3389)
    text = rdpfile.render(p)
    assert "full address:s:pc.corp\n" in text  # no :3389 suffix
    assert rdpfile.parse(text, "x").port == 3389


def test_parse_windows_style_rdp():
    text = (
        "full address:s:host.example:3391\n"
        "username:s:alice\n"
        "screen mode id:i:1\n"
        "desktopwidth:i:1280\n"
        "desktopheight:i:800\n"
        "redirectclipboard:i:0\n"
        "audiomode:i:2\n"
        "drivestoredirect:s:\n"
        "enablecredsspsupport:i:0\n"
        "connection type:i:1\n"
    )
    p = rdpfile.parse(text, "imported")
    assert p.host == "host.example" and p.port == 3391
    assert p.username == "alice"
    assert p.fullscreen is False and p.width == 1280 and p.height == 800
    assert p.clipboard is False and p.audio_output is False
    assert p.drive_redirect is False and p.nla is False
    assert p.quality == "wan"


def test_parse_ipv6_host_is_not_mangled():
    # a bare IPv6 literal has no port suffix — `rpartition(":")` used to split it
    # into host `fe80::1` → `fe80:` / port `1`.
    p = rdpfile.parse("full address:s:fe80::1\n", "v6")
    assert p.host == "fe80::1" and p.port == 3389
    # bracketed, with an explicit port
    p = rdpfile.parse("full address:s:[2001:db8::5]:3391\n", "v6p")
    assert p.host == "2001:db8::5" and p.port == 3391
    # bracketed, default port
    p = rdpfile.parse("full address:s:[2001:db8::5]\n", "v6b")
    assert p.host == "2001:db8::5" and p.port == 3389


def test_ipv6_round_trips_with_a_nondefault_port():
    p = _profile(host="2001:db8::5", port=3391)
    text = rdpfile.render(p)
    assert "full address:s:[2001:db8::5]:3391\n" in text  # bracketed so the port is unambiguous
    assert rdpfile.parse(text, p.name) == p


# ---- commands (FreeRDP argv) -------------------------------------------
def test_build_argv_core_flags():
    argv = commands.build_argv(_profile(), share_path="/home/bob")
    assert argv[0] == "sdl-freerdp"
    assert "/v:pc.corp:3390" in argv
    assert "/u:bob" in argv and "/d:CORP" in argv
    assert "/f" in argv and "/multimon" in argv and "/dynamic-resolution" in argv
    assert "+clipboard" in argv
    assert "/drive:HeDE,/home/bob" in argv
    assert "/sound" in argv and "/microphone" in argv and "/printer" in argv
    assert "/gateway:g:gw.corp" in argv
    assert "/sec:nla" in argv
    assert "/network:lan" in argv and "/gfx:AVC444" in argv
    assert "/cert:tofu" in argv and "/from-stdin" in argv


def test_build_argv_never_contains_password():
    argv = commands.build_argv(_profile(), share_path="/home/bob")
    assert not any(a.startswith("/p:") or a.startswith("/password") for a in argv)


def test_build_argv_windowed_and_toggles_off():
    argv = commands.build_argv(
        _profile(fullscreen=False, clipboard=False, audio_output=False,
                 microphone=False, printers=False, nla=False, multimon=False,
                 drive_redirect=False, quality="balanced"),
        share_path="/home/bob")
    assert "/size:2560x1440" in argv and "/f" not in argv
    assert "-clipboard" in argv and "-sound" in argv
    assert "/microphone" not in argv and "/printer" not in argv
    assert "/sec:rdp" in argv and "/sec:nla" not in argv
    assert not any(a.startswith("/drive:") for a in argv)  # no share
    assert "/network:auto" in argv  # balanced


def test_drive_needs_share_path():
    argv = commands.build_argv(_profile(drive_redirect=True), share_path=None)
    assert not any(a.startswith("/drive:") for a in argv)


# ---- store -------------------------------------------------------------
def test_store_save_list_load_delete(tmp_path):
    p = _profile()
    path = store.save_profile(p, base=str(tmp_path))
    assert path.exists()
    assert store.list_profiles(base=str(tmp_path)) == ["Work PC"]
    assert store.load_profile("Work PC", base=str(tmp_path)) == p
    assert store.load_profile("missing", base=str(tmp_path)) is None
    assert store.delete_profile("Work PC", base=str(tmp_path)) is True
    assert store.list_profiles(base=str(tmp_path)) == []


def test_store_rejects_unsafe_names(tmp_path):
    for bad in ("../evil", "a/b", "", ".hidden"):
        try:
            store.profile_path(bad, base=str(tmp_path))
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {bad!r}")


# ---- launcher (Customs integration) ------------------------------------
def test_desktop_id_slug():
    assert launcher.desktop_id("Work PC") == "gangway-work-pc"
    assert launcher.desktop_id("home.lan!") == "gangway-home-lan"


def test_desktop_entry_and_customs_round_trip():
    entry = launcher.desktop_entry(_profile())
    assert entry.name == "Work PC (RDP)"
    assert entry.exec == 'gangway-open "Work PC"'  # quoted (has a space)
    # a per-profile launcher opens ITS profile — it must NOT claim to handle every
    # .rdp file; that belongs to the dedicated handler (below).
    assert entry.mime_types == []
    assert entry.startup_wm_class == "sdl-freerdp"
    assert entry.extra["X-Gangway-Profile"] == "Work PC"
    # it renders and parses back through Customs
    back = DesktopEntry.parse(entry.render())
    assert back.exec == entry.exec and back.startup_wm_class == entry.startup_wm_class


def test_handler_desktop_entry_carries_mime_types():
    entry = launcher.handler_desktop_entry()
    assert entry.exec == "gangway-rdp-open %u"  # %u passes the file/URI to the stub
    assert "application/x-rdp" in entry.mime_types
    assert "x-scheme-handler/rdp" in entry.mime_types
    assert entry.no_display is True  # a handler, not a menu entry
    back = DesktopEntry.parse(entry.render())
    assert back.mime_types == entry.mime_types and back.no_display is True


def test_launcher_has_fullscreen_and_windowed_jumplist():
    entry = launcher.desktop_entry(_profile())
    actions = {a.id: a for a in entry.actions}
    assert set(actions) == {"fullscreen", "windowed"}
    assert actions["fullscreen"].exec == 'gangway-open "Work PC" --fullscreen'
    assert actions["windowed"].exec == 'gangway-open "Work PC" --windowed'
    # survives the Customs render/parse round-trip.
    back = DesktopEntry.parse(entry.render())
    assert {a.id for a in back.actions} == {"fullscreen", "windowed"}
