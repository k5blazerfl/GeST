"""Tests for keychainctl. Pure tests (parser/format/rows) always run; the
end-to-end command flows are gated on ``cryptography`` so they run in CI and
skip on a host without it."""

from __future__ import annotations

import importlib.util

import pytest

from gest.core.keychain.model import Collection, Item, VaultPayload
from gest.tui.keychain import cli
from gest.tui.keychain.viewer import build_rows

_HAS_CRYPTO = importlib.util.find_spec("cryptography") is not None
requires_crypto = pytest.mark.skipif(not _HAS_CRYPTO, reason="cryptography not installed")


# ---- scripted IO -------------------------------------------------------
def make_io(passphrases=(), secrets=()):
    out: list[str] = []
    err: list[str] = []
    box = {"bytes": b""}
    pp = iter(passphrases)
    sec = iter(secrets)

    def out_bytes(b: bytes) -> None:
        box["bytes"] += b

    io = cli.CliIO(
        out=out.append,
        err=err.append,
        out_bytes=out_bytes,
        ask_passphrase=lambda prompt: next(pp),
        ask_secret=lambda prompt: next(sec),
    )
    return io, out, err, box


def cheap_vault_cls():
    """A Vault subclass that creates vaults with a fast Argon2id so tests aren't
    dominated by the KDF; unlock reads the stored (cheap) params."""
    from gest.core.keychain.crypto import KdfParams
    from gest.core.keychain.vault import Vault

    class CheapVault(Vault):
        @classmethod
        def create(cls, path, passphrase, *, kdf_params=None):
            params = kdf_params or KdfParams.generate(time_cost=1, memory_cost=8, parallelism=1)
            return super().create(path, passphrase, kdf_params=params)

        def change_passphrase(self, new_passphrase, *, kdf_params=None):
            params = kdf_params or KdfParams.generate(time_cost=1, memory_cost=8, parallelism=1)
            super().change_passphrase(new_passphrase, kdf_params=params)

    return CheapVault


# ---- pure tests --------------------------------------------------------
def test_parse_attrs_ok():
    assert cli.parse_attrs(["a=1", "b=2"]) == {"a": "1", "b": "2"}
    assert cli.parse_attrs(["k="]) == {"k": ""}  # empty value allowed


def test_parse_attrs_rejects_bad_token():
    for bad in ["noeq", "=v"]:
        with pytest.raises(ValueError):
            cli.parse_attrs([bad])


def test_format_item_line_has_no_secret():
    it = Item(id="abc", label="rdp", attributes={"host": "pc", "user": "bob"}, secret=b"NOPE")
    line = cli.format_item_line("cid", it)
    assert "abc" in line and "rdp" in line and "host=pc" in line and "user=bob" in line
    assert "NOPE" not in line


def test_parser_requires_a_subcommand():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])


def test_parser_accepts_each_command():
    for argv in (["init"], ["ls"], ["view"], ["passwd"],
                 ["add", "default", "lbl", "--attr", "k=v"],
                 ["search", "--attr", "k=v"], ["get", "someid"], ["rm", "someid"],
                 ["mkcollection", "extra", "--alias", "x"]):
        args = cli.build_parser().parse_args(argv)
        assert args.command == argv[0]


def test_build_rows_empty_vault():
    assert build_rows([]) == ["(empty vault)"]


def test_build_rows_lists_collections_and_items_without_secrets():
    p = VaultPayload()
    col = p.add_collection("login", aliases=["default"])
    p.add_item(col.id, "rdp", {"host": "pc"}, b"TOPSECRET")
    rows = build_rows(list(p.collections.values()))
    joined = "\n".join(rows)
    assert "login" in joined and "default" in joined
    assert "rdp" in joined and "host=pc" in joined
    assert "TOPSECRET" not in joined


def test_build_rows_accepts_collection_objects():
    col = Collection(id="c1", label="misc")
    assert any("misc" in r for r in build_rows([col]))


# ---- end-to-end (need cryptography) ------------------------------------
@requires_crypto
def test_init_add_search_get_roundtrip(tmp_path):
    path = str(tmp_path / "v.vault")
    vc = cheap_vault_cls()

    io, out, err, _ = make_io(passphrases=["pw", "pw"])
    assert cli.run(["--vault", path, "init"], io=io, vault_cls=vc) == 0

    io, out, err, _ = make_io(passphrases=["pw"], secrets=["s3cr3t"])
    rc = cli.run(["--vault", path, "add", "default", "work rdp", "--attr", "host=pc"],
                 io=io, vault_cls=vc)
    assert rc == 0
    item_id = out[-1]

    io, out, err, _ = make_io(passphrases=["pw"])
    assert cli.run(["--vault", path, "search", "--attr", "host=pc"], io=io, vault_cls=vc) == 0
    assert any(item_id in line for line in out)
    assert not any("s3cr3t" in line for line in out)  # search never prints secrets

    io, out, err, box = make_io(passphrases=["pw"])
    assert cli.run(["--vault", path, "get", item_id], io=io, vault_cls=vc) == 0
    assert box["bytes"] == b"s3cr3t"


@requires_crypto
def test_get_by_attribute(tmp_path):
    path = str(tmp_path / "v.vault")
    vc = cheap_vault_cls()
    io, *_ = make_io(passphrases=["pw", "pw"])
    cli.run(["--vault", path, "init"], io=io, vault_cls=vc)
    io, *_ = make_io(passphrases=["pw"], secrets=["hunter2"])
    cli.run(["--vault", path, "add", "default", "l", "--attr", "u=alice"], io=io, vault_cls=vc)

    io, out, err, box = make_io(passphrases=["pw"])
    assert cli.run(["--vault", path, "get", "--attr", "u=alice"], io=io, vault_cls=vc) == 0
    assert box["bytes"] == b"hunter2"


@requires_crypto
def test_get_ambiguous_attribute_errors(tmp_path):
    path = str(tmp_path / "v.vault")
    vc = cheap_vault_cls()
    io, *_ = make_io(passphrases=["pw", "pw"])
    cli.run(["--vault", path, "init"], io=io, vault_cls=vc)
    for secret in ("one", "two"):
        io, *_ = make_io(passphrases=["pw"], secrets=[secret])
        cli.run(["--vault", path, "add", "default", "l", "--attr", "k=dup"], io=io, vault_cls=vc)

    io, out, err, box = make_io(passphrases=["pw"])
    rc = cli.run(["--vault", path, "get", "--attr", "k=dup"], io=io, vault_cls=vc)
    assert rc == 1
    assert box["bytes"] == b""
    assert any("match" in e for e in err)


@requires_crypto
def test_get_requires_exactly_one_selector(tmp_path):
    path = str(tmp_path / "v.vault")
    vc = cheap_vault_cls()
    io, *_ = make_io(passphrases=["pw", "pw"])
    cli.run(["--vault", path, "init"], io=io, vault_cls=vc)
    # neither id nor --attr
    io, out, err, _ = make_io(passphrases=["pw"])
    assert cli.run(["--vault", path, "get"], io=io, vault_cls=vc) == 2


@requires_crypto
def test_wrong_passphrase_fails(tmp_path):
    path = str(tmp_path / "v.vault")
    vc = cheap_vault_cls()
    io, *_ = make_io(passphrases=["right", "right"])
    cli.run(["--vault", path, "init"], io=io, vault_cls=vc)

    io, out, err, _ = make_io(passphrases=["wrong"])
    rc = cli.run(["--vault", path, "ls"], io=io, vault_cls=vc)
    assert rc == 1
    assert err  # an error was reported


@requires_crypto
def test_init_refuses_to_clobber(tmp_path):
    path = str(tmp_path / "v.vault")
    vc = cheap_vault_cls()
    io, *_ = make_io(passphrases=["pw", "pw"])
    assert cli.run(["--vault", path, "init"], io=io, vault_cls=vc) == 0
    io, out, err, _ = make_io(passphrases=["pw2", "pw2"])
    assert cli.run(["--vault", path, "init"], io=io, vault_cls=vc) == 1


@requires_crypto
def test_rm_and_passwd(tmp_path):
    path = str(tmp_path / "v.vault")
    vc = cheap_vault_cls()
    io, *_ = make_io(passphrases=["old", "old"])
    cli.run(["--vault", path, "init"], io=io, vault_cls=vc)
    io, out, *_ = make_io(passphrases=["old"], secrets=["x"])
    cli.run(["--vault", path, "add", "default", "l", "--attr", "a=1"], io=io, vault_cls=vc)
    item_id = out[-1]

    io, out, err, _ = make_io(passphrases=["old"])
    assert cli.run(["--vault", path, "rm", item_id], io=io, vault_cls=vc) == 0

    # change passphrase, then old must fail and new must work
    io, *_ = make_io(passphrases=["old", "new", "new"])
    assert cli.run(["--vault", path, "passwd"], io=io, vault_cls=vc) == 0
    io, out, err, _ = make_io(passphrases=["old"])
    assert cli.run(["--vault", path, "ls"], io=io, vault_cls=vc) == 1
    io, out, err, _ = make_io(passphrases=["new"])
    assert cli.run(["--vault", path, "ls"], io=io, vault_cls=vc) == 0
