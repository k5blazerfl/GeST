"""CI-safe tests for the stage3 module: index parsing + URL building, the
variant model, ``.DIGESTS`` parsing, the mandatory hash verification, and the
argv builders. All pure — no network, no download, no unpack."""

import hashlib

import pytest

from gest.core.stage3 import commands, index, model, verify

# --- fixtures ---------------------------------------------------------------

# A captured latest-stage3-*.txt pointer: comment lines then one data line.
LATEST_INDEX = """\
# Latest as of Sun, 28 Jul 2024 17:30:00 +0000
# ts=1722188400
20240728T170331Z/stage3-amd64-openrc-20240728T170331Z.tar.xz 268435456
"""

STAGE3_FILE = "stage3-amd64-openrc-20240728T170331Z.tar.xz"

# A .DIGESTS in the shape this module documents: `# <ALGO> <hexhash>` header
# followed by the filename line. Includes an unrelated file to prove basename
# matching, and an extra algorithm (MD5) that must be ignored.
DIGESTS_TEXT = f"""\
# MD5 0123456789abcdef0123456789abcdef
{STAGE3_FILE}
# BLAKE2B aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaabbbbbbbbbbbbbbbb
{STAGE3_FILE}
# SHA512 ccccccccccccccccccccccccccccccccdddddddddddddddddddddddddddddddd
{STAGE3_FILE}
# BLAKE2B ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff
stage3-amd64-desktop-openrc-20240728T170331Z.tar.xz
"""


# --- index parsing ----------------------------------------------------------

def test_parse_latest_skips_comments_and_returns_relpath_and_size():
    relpath, size = index.parse_latest(LATEST_INDEX)
    assert relpath == f"20240728T170331Z/{STAGE3_FILE}"
    assert size == 268435456


def test_parse_latest_ignores_trailing_fields():
    text = f"20240728T170331Z/{STAGE3_FILE} 268435456 extra ignored\n"
    relpath, size = index.parse_latest(text)
    assert relpath == f"20240728T170331Z/{STAGE3_FILE}"
    assert size == 268435456


def test_parse_latest_raises_when_no_data_line():
    with pytest.raises(ValueError):
        index.parse_latest("# only a comment\n\n")


# --- URL building -----------------------------------------------------------

def test_latest_url():
    assert index.latest_url(index.MIRROR, "amd64", "openrc") == (
        "https://distfiles.gentoo.org/releases/amd64/autobuilds/"
        "latest-stage3-openrc.txt")
    # the systemd default flavor resolves the same way (flavor is just the token)
    assert index.latest_url(index.MIRROR, "amd64", "systemd") == (
        "https://distfiles.gentoo.org/releases/amd64/autobuilds/"
        "latest-stage3-systemd.txt")


def test_latest_url_honours_custom_mirror_and_strips_trailing_slash():
    assert index.latest_url("https://mirror.example/gentoo/", "amd64",
                            "hardened-openrc") == (
        "https://mirror.example/gentoo/releases/amd64/autobuilds/"
        "latest-stage3-hardened-openrc.txt")


def test_tarball_and_derived_urls():
    relpath = f"20240728T170331Z/{STAGE3_FILE}"
    url = index.tarball_url(index.MIRROR, "amd64", relpath)
    assert url == (
        "https://distfiles.gentoo.org/releases/amd64/autobuilds/"
        f"20240728T170331Z/{STAGE3_FILE}")
    assert index.digests_url(url) == url + ".DIGESTS"
    assert index.signature_url(url) == url + ".asc"


# --- variant model ----------------------------------------------------------

def test_variants_offer_systemd_default_and_openrc_amd64():
    assert model.VARIANTS  # non-empty
    flavors = [v.flavor for v in model.VARIANTS]
    # systemd is the default (HeDE needs it) and comes first
    assert model.DEFAULT_VARIANT.flavor == "systemd"
    assert flavors[0] == "systemd"
    assert {"systemd", "desktop-systemd"} <= set(flavors)
    # OpenRC variants remain for a plain-Gentoo install
    assert {"openrc", "desktop-openrc", "hardened-openrc", "nomultilib-openrc"} <= set(flavors)
    assert all(v.arch == "amd64" for v in model.VARIANTS)


def test_arm64_variants_and_variants_for():
    # Apple Silicon (Asahi) groundwork: arm64 variants (systemd first, like amd64),
    # kept out of the default offered list; variants_for() dispatches per arch.
    assert model.variants_for("amd64") is model.VARIANTS
    assert model.variants_for("arm64") is model.ARM64_VARIANTS
    assert model.ARM64_VARIANTS and all(v.arch == "arm64" for v in model.ARM64_VARIANTS)
    assert model.ARM64_VARIANTS[0].flavor == "systemd"    # systemd default on arm64 too
    assert "arm64" in model.SUPPORTED_ARCHES


def test_arm64_stage3_url_uses_the_arm64_autobuilds_path():
    url = index.latest_url(index.MIRROR, "arm64", "openrc")
    assert "/releases/arm64/autobuilds/" in url
    assert url.endswith("latest-stage3-openrc.txt")


def test_selection_carries_the_resolved_urls():
    sel = model.Stage3Selection(
        url="https://m/x/stage3.tar.xz", filename="stage3.tar.xz", size=42,
        digests_url="https://m/x/stage3.tar.xz.DIGESTS",
        signature_url="https://m/x/stage3.tar.xz.asc")
    assert sel.size == 42
    assert sel.digests_url.endswith(".DIGESTS")
    assert sel.signature_url.endswith(".asc")


# --- .DIGESTS parsing -------------------------------------------------------

def test_parse_digests_returns_blake2b_and_sha512_for_named_file():
    got = verify.parse_digests(DIGESTS_TEXT, STAGE3_FILE)
    assert got == {
        "BLAKE2B": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaabbbbbbbbbbbbbbbb",
        "SHA512": "ccccccccccccccccccccccccccccccccdddddddddddddddddddddddddddddddd",
    }
    assert "MD5" not in got  # only BLAKE2B/SHA512 are kept


def test_parse_digests_matches_on_basename():
    got = verify.parse_digests(DIGESTS_TEXT, f"/some/dir/{STAGE3_FILE}")
    assert set(got) == {"BLAKE2B", "SHA512"}


def test_parse_digests_returns_nothing_for_unknown_file():
    assert verify.parse_digests(DIGESTS_TEXT, "stage3-nonexistent.tar.xz") == {}


def test_parse_digests_handles_live_mirror_shape():
    # The real Gentoo shape: `# <ALGO> HASH` header then `<hex>  <filename>`.
    blake = "1" * 128
    sha = "2" * 128
    text = (f"# BLAKE2B HASH\n{blake}  {STAGE3_FILE}\n"
            f"# SHA512 HASH\n{sha}  {STAGE3_FILE}\n")
    assert verify.parse_digests(text, STAGE3_FILE) == {
        "BLAKE2B": blake, "SHA512": sha}


# --- hashing + verification -------------------------------------------------

def test_hashes_of_matches_hashlib():
    data = b"a small known stage3-ish blob\n"
    got = verify.hashes_of(data)
    assert got["BLAKE2B"] == hashlib.blake2b(data).hexdigest()
    assert got["SHA512"] == hashlib.sha512(data).hexdigest()


def test_verify_hashes_accepts_correct_and_rejects_tampered():
    data = b"the real tarball bytes"
    expected = verify.hashes_of(data)
    assert verify.verify_hashes(data, expected) is True
    # A single flipped hash must fail the whole check.
    tampered = dict(expected)
    tampered["SHA512"] = "0" * 128
    assert verify.verify_hashes(data, tampered) is False
    # Wrong data against good expected also fails.
    assert verify.verify_hashes(b"different bytes", expected) is False


def test_verify_hashes_is_case_insensitive():
    data = b"case blob"
    expected = {k: v.upper() for k, v in verify.hashes_of(data).items()}
    assert verify.verify_hashes(data, expected) is True


def test_verify_hashes_rejects_empty_expected():
    # An unverifiable download (no digest for the file) can never pass.
    assert verify.verify_hashes(b"anything", {}) is False


def test_end_to_end_parse_then_verify():
    data = b"pretend this is the stage3 tarball content"
    hashes = verify.hashes_of(data)
    digests = (f"# BLAKE2B {hashes['BLAKE2B']}\n{STAGE3_FILE}\n"
               f"# SHA512 {hashes['SHA512']}\n{STAGE3_FILE}\n")
    expected = verify.parse_digests(digests, STAGE3_FILE)
    assert verify.verify_hashes(data, expected) is True


# --- argv builders ----------------------------------------------------------

def test_tar_unpack_argv_has_handbook_flags_and_target_root():
    argv = commands.tar_unpack_argv("/mnt/gentoo/.gest/stage3.tar.xz", "/mnt/gentoo")
    assert argv == [
        "tar", "xpf", "/mnt/gentoo/.gest/stage3.tar.xz", "-C", "/mnt/gentoo",
        "--xattrs-include=*.*", "--numeric-owner"]
    # The target root is the -C argument.
    assert argv[argv.index("-C") + 1] == "/mnt/gentoo"
    assert "--numeric-owner" in argv
    assert "--xattrs-include=*.*" in argv


def test_tar_unpack_argv_honours_custom_tar():
    argv = commands.tar_unpack_argv("/t.tar.xz", "/mnt/x", tar="/bin/tar")
    assert argv[0] == "/bin/tar"


def test_gpg_verify_argv():
    assert commands.gpg_verify_argv("/t.asc", "/t.tar.xz") == [
        "gpg", "--verify", "/t.asc", "/t.tar.xz"]
    assert commands.gpg_verify_argv("/t.asc", "/t.tar.xz", gpg="/usr/bin/gpg")[0] == (
        "/usr/bin/gpg")
