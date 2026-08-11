"""Tests for the main-repo rsync mirror list and gentoo.conf sync-uri rewrite."""

from gest.core.repos import mirrors

_URI = "rsync://rsync.de.gentoo.org/gentoo-portage"


def test_mirrors_are_rsync_uris_with_module():
    ms = mirrors.mirrors()
    assert ms[0][0].startswith("Default")
    assert all(uri.startswith("rsync://") and uri.endswith("/gentoo-portage")
               for _label, uri in ms)
    # the global rotation is offered
    assert ("Default (global rotation)",
            "rsync://rsync.gentoo.org/gentoo-portage") in ms


def test_set_sync_uri_replaces_existing_line_preserving_the_rest():
    text = (
        "[gentoo]\n"
        "location = /var/db/repos/gentoo\n"
        "sync-type = rsync\n"
        "sync-uri = rsync://rsync.gentoo.org/gentoo-portage\n"
        "auto-sync = yes\n"
        "sync-openpgp-key-path = /usr/share/openpgp-keys/gentoo-release.asc\n"
    )
    out = mirrors.set_sync_uri(text, "gentoo", _URI)
    assert f"sync-uri = {_URI}" in out
    assert "rsync://rsync.gentoo.org" not in out          # old value gone
    # everything else preserved
    assert "location = /var/db/repos/gentoo" in out
    assert "sync-openpgp-key-path = /usr/share/openpgp-keys/gentoo-release.asc" in out
    assert out.count("sync-uri = ") == 1


def test_set_sync_uri_inserts_when_section_has_no_sync_uri():
    text = "[gentoo]\nlocation = /var/db/repos/gentoo\nsync-type = rsync\n"
    out = mirrors.set_sync_uri(text, "gentoo", _URI)
    assert f"sync-uri = {_URI}" in out
    assert "location = /var/db/repos/gentoo" in out


def test_set_sync_uri_creates_override_when_absent():
    out = mirrors.set_sync_uri("", "gentoo", _URI)
    assert out == f"[gentoo]\nsync-uri = {_URI}\n"


def test_set_sync_uri_appends_section_when_other_sections_present():
    text = "[myoverlay]\nlocation = /var/db/repos/myoverlay\n"
    out = mirrors.set_sync_uri(text, "gentoo", _URI)
    assert "[myoverlay]" in out and "[gentoo]" in out
    assert f"sync-uri = {_URI}" in out
    # only the gentoo section gained a sync-uri
    assert out.count("sync-uri = ") == 1


def test_set_sync_uri_only_touches_the_named_section():
    text = (
        "[gentoo]\nsync-uri = rsync://old/gentoo-portage\n"
        "[other]\nsync-uri = rsync://other/thing\n"
    )
    out = mirrors.set_sync_uri(text, "gentoo", _URI)
    assert f"sync-uri = {_URI}" in out
    assert "rsync://other/thing" in out                   # other section untouched
    assert "rsync://old/gentoo-portage" not in out
