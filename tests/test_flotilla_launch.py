"""CI-safe tests for `flotilla launch` — the turnkey create→fetch→define→boot flow.
All host ops run through an injected run_argv; nothing is fetched or booted."""

from __future__ import annotations

import dataclasses
from xml.etree import ElementTree as ET

from gest.core.flotilla import vessels
from gest.tui.flotilla.cli import CliIO, FlotillaEnv, run_cli


class _H:
    def __init__(self, tmp_path):
        self.out: list[str] = []
        self.err: list[str] = []
        self.calls: list = []
        self.store = str(tmp_path / "vessels")
        self.env = FlotillaEnv(io=CliIO(out=self.out.append, err=self.err.append),
                               store_base=self.store, cache_base=str(tmp_path / "cache"),
                               run_argv=lambda a: self.calls.append(a) or 0)

    def verbs(self):
        return [c[3] if c and c[0] == "virsh" else (c[0] if c else "") for c in self.calls]


def test_launch_new_linux_full_flow(tmp_path):
    h = _H(tmp_path)
    assert run_cli(["launch", "Debian", "--os", "linux", "--iso", "/iso/debian.iso"],
                   env=h.env) == 0
    v = vessels.load_vessel("debian", h.store)
    assert v is not None and v.install_iso == "/iso/debian.iso"
    # allocate → define → start → console, in order.
    assert h.verbs() == ["qemu-img", "define", "start", "virt-viewer"]


def test_launch_catalog_iso_is_fetched(tmp_path):
    h = _H(tmp_path)
    assert run_cli(["launch", "arch-box", "--os", "linux", "--iso", "arch"], env=h.env) == 0
    v = vessels.load_vessel("arch-box", h.store)
    assert v.install_iso.endswith("/images/archlinux-x86_64.iso")  # resolved to the cache
    assert h.calls[0][0] == "curl"  # fetched first


def test_launch_windows_aborts_when_virtio_win_fetch_fails(tmp_path):
    # curl fails → _ensure_url_image returns "" → the vessel's virtio_iso would point
    # at a missing ISO. Launch must abort here with a clear message, not go on to
    # define a domain whose <cdrom> references a nonexistent file.
    h = _H(tmp_path)
    failing = dataclasses.replace(h.env, run_argv=lambda a: 1)  # the virtio-win curl fails
    rc = run_cli(["launch", "Win11", "--os", "windows", "--iso", "/iso/win.iso"], env=failing)
    assert rc == 1
    assert any("virtio-win" in e for e in h.err)


def test_launch_no_start(tmp_path):
    h = _H(tmp_path)
    assert run_cli(["launch", "deb", "--no-start"], env=h.env) == 0
    assert "start" not in h.verbs() and "virt-viewer" not in h.verbs()


def test_launch_no_console(tmp_path):
    h = _H(tmp_path)
    assert run_cli(["launch", "deb", "--no-console"], env=h.env) == 0
    assert "start" in h.verbs() and "virt-viewer" not in h.verbs()


def test_launch_existing_vessel_is_reused_not_reallocated(tmp_path):
    h = _H(tmp_path)
    run_cli(["create", "deb", "--os", "linux", "--no-allocate"], env=h.env)
    h.calls.clear()
    assert run_cli(["launch", "deb", "--no-start"], env=h.env) == 0
    assert any("using vessel deb" in line for line in h.out)
    assert "qemu-img" not in h.verbs()  # existing → no re-allocate (would clobber)


def test_launch_windows_mido_id_is_rejected(tmp_path):
    h = _H(tmp_path)
    assert run_cli(["launch", "win11", "--os", "windows", "--iso", "win11"], env=h.env) == 2
    assert any("needs mido" in e for e in h.err)
    assert h.calls == []


# ---- guest enablement (--provision / --remote-app) ---------------------
def test_launch_windows_remote_app_builds_unattend_iso(tmp_path):
    from gest.core.flotilla import domainxml, vessels
    h = _H(tmp_path)
    rc = run_cli(["launch", "Win11", "--os", "windows", "--iso", "/iso/win.iso",
                  "--remote-app", r"Notepad=C:\Windows\notepad.exe",
                  "--username", "skipper", "--no-start"], env=h.env)
    assert rc == 0
    # xorriso built the provisioning ISO, before `virsh define`.
    assert "xorriso" in h.verbs()
    assert h.verbs().index("xorriso") < h.verbs().index("define")
    v = vessels.load_vessel("win11", h.store)
    assert v.provisioned and v.unattend_username == "skipper"
    assert v.entry == "rdp"  # a provisioned vessel opens seamless by default
    assert v.remote_app_programs[0].name == "Notepad"
    assert v.unattend_iso.endswith("/win11/unattend.iso")
    # the staged files were written and the domain attaches the disc at sdm.
    staged = tmp_path / "vessels" / "win11" / "unattend"
    assert (staged / "autounattend.xml").is_file() and (staged / "firstboot.ps1").is_file()
    root = ET.fromstring(domainxml.compile_domain(v))
    cdroms = {c.find("target").get("dev") for c in root.findall("devices/disk[@device='cdrom']")}
    assert "sdm" in cdroms


def test_provision_flag_without_programs_is_permissive(tmp_path):
    from gest.core.flotilla import vessels
    h = _H(tmp_path)
    assert run_cli(["launch", "Win11", "--os", "windows", "--iso", "/iso/win.iso",
                    "--provision", "--no-start"], env=h.env) == 0
    v = vessels.load_vessel("win11", h.store)
    assert v.provisioned and v.remote_app_programs == []
    assert v.unattend_username == "flotilla"  # the default account


def test_provision_rejected_for_linux(tmp_path):
    h = _H(tmp_path)
    rc = run_cli(["launch", "deb", "--os", "linux", "--iso", "/iso/deb.iso",
                  "--provision", "--no-start"], env=h.env)
    assert rc == 1
    assert any("Windows path" in e for e in h.err)
    assert "xorriso" not in h.verbs() and "define" not in h.verbs()


def test_provision_aborts_when_xorriso_fails(tmp_path):
    # xorriso fails → abort before defining a domain that points <cdrom> at a
    # nonexistent unattend ISO (the same discipline as the virtio-win guard).
    h = _H(tmp_path)
    def run(argv):
        h.calls.append(argv)
        return 1 if argv and argv[0] == "xorriso" else 0
    env = dataclasses.replace(h.env, run_argv=run)
    rc = run_cli(["launch", "Win11", "--os", "windows", "--iso", "/iso/win.iso",
                  "--remote-app", r"C:\Windows\notepad.exe", "--no-start"], env=env)
    assert rc == 1
    assert any("guest-enablement ISO" in e for e in h.err)
    assert "define" not in h.verbs()


def test_create_windows_remote_app_provisions(tmp_path):
    from gest.core.flotilla import vessels
    h = _H(tmp_path)
    rc = run_cli(["create", "Win11", "--os", "windows", "--no-allocate",
                  "--remote-app", r"C:\Windows\System32\mspaint.exe"], env=h.env)
    assert rc == 0
    v = vessels.load_vessel("win11", h.store)
    assert v.provisioned and v.remote_app_programs[0].key == "mspaint"
    assert "xorriso" in h.verbs()
