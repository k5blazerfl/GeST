"""CI-safe tests for resolving a .rdp file / rdp:// URI to a transient profile."""

from __future__ import annotations

from gest.core.rdp import target


def test_is_uri():
    assert target.is_uri("rdp://host")
    assert not target.is_uri("/path/to/file.rdp")
    assert not target.is_uri("file:///path/x.rdp")


def test_profile_from_uri_full():
    p = target.profile_from_uri("rdp://alice@pc.corp:3390")
    assert p.host == "pc.corp" and p.port == 3390 and p.username == "alice"
    assert p.name == "pc.corp"


def test_profile_from_uri_bare_host_defaults_port():
    p = target.profile_from_uri("rdp://box")
    assert p.host == "box" and p.port == 3389 and p.username == ""


def test_profile_from_uri_bad_port_falls_back():
    p = target.profile_from_uri("rdp://box:notaport")
    assert p.port == 3389


def test_local_path_strips_file_scheme():
    assert target.local_path("file:///home/u/a.rdp") == "/home/u/a.rdp"
    assert target.local_path("/home/u/a.rdp") == "/home/u/a.rdp"


def test_profile_from_file(tmp_path):
    rdp = tmp_path / "work.rdp"
    rdp.write_text("full address:s:pc.corp\nusername:s:bob\ndomain:s:CORP\n")
    p = target.profile_from_file(str(rdp))
    assert p.host == "pc.corp" and p.username == "bob" and p.domain == "CORP"
    assert p.name == "work"  # the file stem


def test_profile_from_target_dispatches():
    assert target.profile_from_target("rdp://h").host == "h"


def test_profile_from_file_via_file_url(tmp_path):
    rdp = tmp_path / "x.rdp"
    rdp.write_text("full address:s:h:3389\n")
    assert target.profile_from_target(f"file://{rdp}").host == "h"
