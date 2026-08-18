"""CI-safe tests for the Flotilla store, virsh command builders, and CLI.
Host operations run through an injected ``run_argv``, so no libvirt is touched."""

from __future__ import annotations

from gest.core.flotilla import backend, vessels
from gest.core.flotilla.model import OS_WINDOWS, Vessel
from gest.tui.flotilla.cli import CliIO, FlotillaEnv, run_cli


# ---- store -------------------------------------------------------------
def test_store_round_trip(tmp_path):
    base = str(tmp_path)
    v = Vessel(id="win11", name="Windows 11", os=OS_WINDOWS)
    vessels.save_vessel(v, base)
    assert vessels.list_vessels(base) == ["win11"]
    assert vessels.load_vessel("win11", base) == v
    assert vessels.load_vessel("missing", base) is None
    assert vessels.delete_vessel("win11", base) is True
    assert vessels.list_vessels(base) == []


def test_store_rejects_unsafe_ids(tmp_path):
    for bad in ("../evil", "a/b", "", ".hidden", "UPPER"):
        try:
            vessels.vessel_dir(bad, base=str(tmp_path))
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {bad!r}")


# ---- backend argv ------------------------------------------------------
def test_virsh_builders():
    u = backend.URI_SESSION
    assert backend.define_argv(u, "/x/domain.xml") == \
        ["virsh", "--connect", u, "define", "/x/domain.xml"]
    assert backend.start_argv(u, "win11")[-1] == "win11"
    assert backend.destroy_argv(u, "win11")[-2:] == ["destroy", "win11"]
    assert backend.shutdown_argv(u, "win11")[-2:] == ["shutdown", "win11"]
    assert "--nvram" in backend.undefine_argv(u, "win11")
    assert backend.console_argv(u, "win11")[0] == "virt-viewer"
    assert backend.alloc_disk_argv("/x/disk.qcow2", 64) == \
        ["qemu-img", "create", "-f", "qcow2", "/x/disk.qcow2", "64G"]


# ---- CLI ---------------------------------------------------------------
class _H:
    def __init__(self, tmp_path):
        self.out: list[str] = []
        self.err: list[str] = []
        self.calls: list = []
        self.store = str(tmp_path / "vessels")
        self.env = FlotillaEnv(io=CliIO(out=self.out.append, err=self.err.append),
                               store_base=self.store,
                               run_argv=lambda argv: self.calls.append(argv) or 0)


def test_create_saves_a_windows_vessel(tmp_path):
    h = _H(tmp_path)
    assert run_cli(["create", "Windows 11", "--os", "windows", "--memory", "8192",
                    "--iso", "/iso/win11.iso", "--no-allocate"], env=h.env) == 0
    v = vessels.load_vessel("windows-11", h.store)
    assert v is not None and v.os == "windows" and v.memory_mb == 8192
    assert v.secureboot and v.tpm  # recommended Windows defaults
    assert v.disks and v.disks[0].path.endswith("/windows-11/disk.qcow2")
    assert v.virtio_iso.endswith("/virtio-win.iso")  # auto-attached for Windows
    assert h.calls == []  # --no-allocate, so nothing ran


def test_create_allocates_the_disk_by_default(tmp_path):
    h = _H(tmp_path)
    run_cli(["create", "deb", "--os", "linux", "--disk-size", "20"], env=h.env)
    assert h.calls[0][:3] == ["qemu-img", "create", "-f"] and h.calls[0][-1] == "20G"


def test_create_rejects_duplicate(tmp_path):
    h = _H(tmp_path)
    run_cli(["create", "deb"], env=h.env)
    assert run_cli(["create", "deb"], env=h.env) == 1


def test_xml_and_prereqs_are_pure(tmp_path):
    h = _H(tmp_path)
    run_cli(["create", "Win", "--os", "windows"], env=h.env)
    h.out.clear()
    h.calls.clear()  # drop the create-time qemu-img allocate call
    assert run_cli(["xml", "win"], env=h.env) == 0
    assert any("<domain type=\"kvm\">" in line for line in h.out)
    h.out.clear()
    assert run_cli(["prereqs", "win"], env=h.env) == 0
    joined = "\n".join(h.out)
    assert "app-emulation/libvirt" in joined and "swtpm" in joined
    assert h.calls == []  # xml/prereqs never touch the host


def test_define_writes_xml_and_calls_virsh(tmp_path):
    h = _H(tmp_path)
    run_cli(["create", "deb"], env=h.env)
    assert run_cli(["define", "deb"], env=h.env) == 0
    assert (tmp_path / "vessels" / "deb" / "domain.xml").exists()
    assert h.calls[-1][:4] == ["virsh", "--connect", backend.URI_SESSION, "define"]


def test_lifecycle_failures_report_on_stderr(tmp_path):
    import dataclasses
    h = _H(tmp_path)
    run_cli(["create", "deb"], env=h.env)
    failing = dataclasses.replace(h.env, run_argv=lambda argv: 1)  # virsh returns nonzero
    for cmd, word in ((["define", "deb"], "define"), (["start", "deb"], "start"),
                      (["stop", "deb"], "stop")):
        h.out.clear()
        h.err.clear()
        assert run_cli(cmd, env=failing) == 1
        assert any(word in e and "failed" in e for e in h.err)  # failure on stderr…
        assert not any("failed" in o for o in h.out)            # …not stdout


def test_start_stop_console_dispatch(tmp_path):
    h = _H(tmp_path)
    run_cli(["create", "deb"], env=h.env)
    h.calls.clear()
    run_cli(["start", "deb"], env=h.env)
    run_cli(["stop", "deb"], env=h.env)
    run_cli(["stop", "deb", "--force"], env=h.env)
    run_cli(["console", "deb"], env=h.env)
    verbs = [c[3] if c[0] == "virsh" else c[0] for c in h.calls]
    assert verbs == ["start", "shutdown", "destroy", "virt-viewer"]


def test_actions_on_unknown_vessel(tmp_path):
    h = _H(tmp_path)
    assert run_cli(["start", "nope"], env=h.env) == 1
    assert run_cli(["xml", "nope"], env=h.env) == 1
    assert h.calls == []


def test_rm_undefines_and_deletes(tmp_path):
    h = _H(tmp_path)
    run_cli(["create", "deb"], env=h.env)
    assert run_cli(["rm", "deb"], env=h.env) == 0
    assert vessels.list_vessels(h.store) == []
    assert any(c[0] == "virsh" and "undefine" in c for c in h.calls)
