"""CI-safe tests for the Customs foreign-app integration layer."""

from __future__ import annotations

from gest.core.customs import icons, identity, mime
from gest.core.customs.desktop import (
    DesktopAction,
    DesktopEntry,
    build_exec,
    entry_path,
    remove_entry,
    strip_field_codes,
    write_entry,
)


# ---- desktop: Exec quoting + field codes -------------------------------
def test_build_exec_quotes_only_when_needed():
    assert build_exec(["gangway-open", "work"]) == "gangway-open work"
    assert build_exec(["drydock-run", "barrel one", "app"]) == 'drydock-run "barrel one" app'
    assert build_exec(["x", ""]) == 'x ""'


def test_build_exec_escapes_reserved_chars():
    out = build_exec(["run", 'a"b$c`d\\e'])
    assert out.startswith('run "') and '\\"' in out and "\\$" in out and "\\`" in out


def test_strip_field_codes():
    assert strip_field_codes("wine start %f") == "wine start"
    assert strip_field_codes("run %U --flag %i") == "run --flag"


# ---- desktop: render / parse round-trip --------------------------------
def test_render_contains_core_keys():
    entry = DesktopEntry(name="Work RDP", exec="gangway-open work", icon="gangway-work",
                         categories=["Network", "RemoteAccess"],
                         mime_types=[mime.RDP_FILE, mime.RDP_SCHEME],
                         startup_wm_class="freerdp",
                         extra={"X-GeST-Origin": "gangway"})
    text = entry.render()
    assert "[Desktop Entry]" in text and "Type=Application" in text
    assert "Name=Work RDP" in text and "Exec=gangway-open work" in text
    assert "Categories=Network;RemoteAccess;" in text
    assert "MimeType=application/x-rdp;x-scheme-handler/rdp;" in text
    assert "StartupWMClass=freerdp" in text
    assert "X-GeST-Origin=gangway" in text


def test_round_trip_preserves_everything_including_actions():
    entry = DesktopEntry(
        name="Excel", exec="drydock-run office excel", icon="excel",
        comment="Spreadsheets", categories=["Office"], mime_types=[mime.EXE],
        startup_wm_class="excel.exe", no_display=False,
        actions=[DesktopAction(id="new", name="New Document", exec="drydock-run office excel /n")],
        extra={"X-GeST-Barrel": "office"},
    )
    back = DesktopEntry.parse(entry.render())
    assert back.name == "Excel"
    assert back.exec == "drydock-run office excel"
    assert back.categories == ["Office"]
    assert back.mime_types == [mime.EXE]
    assert back.startup_wm_class == "excel.exe"
    assert back.extra.get("X-GeST-Barrel") == "office"
    assert len(back.actions) == 1
    assert back.actions[0].id == "new" and back.actions[0].name == "New Document"


def test_escaped_values_round_trip():
    entry = DesktopEntry(name="a\tb", exec="run", comment="line1\nline2")
    back = DesktopEntry.parse(entry.render())
    assert back.name == "a\tb"
    assert back.comment == "line1\nline2"


# ---- desktop: filesystem write/remove ----------------------------------
def test_write_read_remove_entry(tmp_path):
    entry = DesktopEntry(name="Gangway PC", exec="gangway-open pc")
    path = write_entry(entry, "gangway-pc", applications_dir=str(tmp_path))
    assert path == entry_path("gangway-pc", str(tmp_path))
    assert path.exists()
    assert DesktopEntry.parse(path.read_text()).name == "Gangway PC"
    # no leftover temp files
    assert [p.name for p in tmp_path.iterdir()] == ["gangway-pc.desktop"]
    assert remove_entry("gangway-pc", applications_dir=str(tmp_path)) is True
    assert remove_entry("gangway-pc", applications_dir=str(tmp_path)) is False


# ---- mime --------------------------------------------------------------
def test_mime_types_and_argv():
    assert mime.RDP_FILE == "application/x-rdp"
    assert "x-scheme-handler/rdp" in mime.GANGWAY_TYPES
    assert mime.EXE in mime.DRYDOCK_TYPES
    argv = mime.register_default_argv("gangway-pc", mime.GANGWAY_TYPES)
    assert argv[:3] == ["xdg-mime", "default", "gangway-pc.desktop"]
    assert argv[3:] == mime.GANGWAY_TYPES
    assert mime.query_default_argv(mime.EXE) == ["xdg-mime", "query", "default", mime.EXE]
    assert mime.update_database_argv("/tmp/apps")[0] == "update-desktop-database"


# ---- icons -------------------------------------------------------------
def test_icon_extract_argv_and_paths():
    argv = icons.extract_argv("/prefix/app.exe", "/out/app.png", index=2)
    assert argv[0] == "wrestool" and "-t" in argv and "14" in argv
    assert argv[-1] == "/prefix/app.exe" and "/out/app.png" in argv
    assert "-n" in argv and "2" in argv
    p = icons.icon_install_path("excel", size="48x48")
    assert p.parts[-3:] == ("48x48", "apps", "excel.png")
    assert icons.scalable_install_path("excel").parts[-3:] == ("scalable", "apps", "excel.svg")


def test_icon_convert_argv():
    argv = icons.convert_argv("/tmp/app.ico", "/out/app.png", width="48")
    assert argv[0] == "icotool" and "-x" in argv
    assert "-w" in argv and "48" in argv
    assert argv[-1] == "/tmp/app.ico" and "/out/app.png" in argv


# ---- identity ----------------------------------------------------------
def test_normalize_wm_class_forms():
    assert identity.normalize("Excel.EXE") == "excel.exe"  # dots kept (reverse-DNS app-ids)
    assert identity.normalize("firefox\x00Firefox") == "firefox"  # X11 WM_CLASS NUL split
    assert identity.normalize("org.FreeRDP.Client") == "org.freerdp.client"
    assert identity.normalize("  Foo  ") == "foo"


def test_identity_map_register_resolve_unregister():
    m = identity.IdentityMap()
    m.register(["freerdp", "org.freerdp.client"], "gangway-pc")
    m.register(["Excel.exe"], "drydock-excel")
    assert m.resolve("FreeRDP") == "gangway-pc"
    assert m.resolve("org.freerdp.client") == "gangway-pc"
    assert m.resolve("excel.EXE") == "drydock-excel"
    assert m.resolve("unknown") is None
    assert m.keys_for("gangway-pc") == ["freerdp", "org.freerdp.client"]
    m.unregister("gangway-pc")
    assert m.resolve("freerdp") is None
    assert m.resolve("excel.exe") == "drydock-excel"  # unaffected


def test_identity_map_dict_round_trip():
    m = identity.IdentityMap()
    m.register(["Excel.exe", "org.freerdp.client"], "drydock-excel")
    restored = identity.IdentityMap.from_dict(m.to_dict())
    assert restored.resolve("excel.exe") == "drydock-excel"
    assert restored.resolve("org.freerdp.client") == "drydock-excel"
    assert m.to_dict()["version"] == identity.IDENTITY_VERSION
    assert identity.IdentityMap.from_dict({}).resolve("x") is None
