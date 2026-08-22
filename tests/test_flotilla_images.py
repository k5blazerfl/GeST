"""CI-safe tests for the Flotilla install-media catalog + `flotilla images`/`fetch`.
Downloads run through an injected run_argv/capture — nothing is fetched."""

from __future__ import annotations

from gest.core.flotilla import images
from gest.tui.flotilla.cli import CliIO, FlotillaEnv, run_cli


# ---- catalog + builders (pure) -----------------------------------------
def test_catalog_has_linux_virtio_and_windows():
    ids = {im.id for im in images.CATALOG}
    assert {"debian", "virtio-win", "win11"} <= ids
    assert images.by_id("win11").fetcher == images.FETCH_MIDO
    assert images.by_id("debian").fetcher == images.FETCH_URL
    assert images.by_id("nope") is None


def test_filename_and_cached_path():
    virtio = images.by_id("virtio-win")
    assert images.filename_for(virtio) == "virtio-win.iso"
    assert images.cached_path(virtio, "/c").endswith("/c/images/virtio-win.iso")
    # url without an explicit filename → basename of the URL
    assert images.filename_for(images.by_id("arch")) == "archlinux-x86_64.iso"
    assert images.filename_for(images.by_id("win11")) == "win11.iso"  # mido edition


def test_argv_builders():
    assert images.curl_argv("http://x/a.iso", "/c/a.iso") == \
        ["curl", "-fL", "--create-dirs", "-o", "/c/a.iso", "http://x/a.iso"]
    m = images.mido_argv("win11", "/cache")
    assert m[:2] == ["sh", "-c"] and "mido win11" in m[2] and "/cache" in m[2]
    assert images.sha256_argv("/c/a.iso") == ["sha256sum", "/c/a.iso"]


def test_unattend_iso_argv():
    argv = images.unattend_iso_argv("/stage/win11", "/vm/win11/unattend.iso", "FLOTILLA")
    assert argv[:4] == ["xorriso", "-as", "mkisofs", "-V"]
    assert argv[4] == "FLOTILLA"  # volume label firstboot locates itself by
    assert "-J" in argv and "-r" in argv  # Joliet + Rock Ridge preserve filenames
    assert argv[argv.index("-o") + 1] == "/vm/win11/unattend.iso"
    assert argv[-1] == "/stage/win11"  # the staging dir is the source


def test_verify_sha256():
    out = "abc123  /cache/images/a.iso\n"
    assert images.verify_sha256(out, "abc123") is True
    assert images.verify_sha256(out, "ABC123") is True  # case-insensitive
    assert images.verify_sha256(out, "deadbeef") is False
    assert images.verify_sha256(out, "") is False  # no expected → not verified
    assert images.verify_sha256("", "abc123") is False


# ---- CLI ---------------------------------------------------------------
class _H:
    def __init__(self, tmp_path, *, sha_output=""):
        self.out: list[str] = []
        self.err: list[str] = []
        self.calls: list = []
        self.env = FlotillaEnv(io=CliIO(out=self.out.append, err=self.err.append),
                               cache_base=str(tmp_path / "cache"),
                               run_argv=lambda a: self.calls.append(a) or 0,
                               capture=lambda a: sha_output)


def test_images_lists_the_catalog(tmp_path):
    h = _H(tmp_path)
    assert run_cli(["images"], env=h.env) == 0
    joined = "\n".join(h.out)
    assert "debian" in joined and "win11" in joined and "[mido]" in joined


def test_fetch_url_image_runs_curl(tmp_path):
    h = _H(tmp_path)
    assert run_cli(["fetch", "arch"], env=h.env) == 0
    assert h.calls[0][0] == "curl"
    assert any("no pinned checksum" in line for line in h.out)  # arch has no sha256


def test_fetch_mido_image_runs_mido(tmp_path):
    h = _H(tmp_path)
    assert run_cli(["fetch", "win11"], env=h.env) == 0
    assert h.calls[0][:2] == ["sh", "-c"] and "mido win11" in h.calls[0][2]


def test_fetch_unknown_image(tmp_path):
    h = _H(tmp_path)
    assert run_cli(["fetch", "beos"], env=h.env) == 1
    assert h.calls == []
