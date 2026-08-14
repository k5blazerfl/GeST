"""``keychainctl`` — a thin CLI over the keychain vault (docs/design/keychain.md).

Create and inspect a vault by hand before the Secret Service daemon exists —
useful for dogfooding and scripting. A secret is written to stdout *only* by an
explicit ``get``; every other command prints metadata, never secrets.

The command layer is pure and TTY-free: each ``cmd_*`` takes the parsed args, a
:class:`CliIO` (prompts + output, injectable) and a vault class, and returns an
exit code. Only :func:`_default_io` touches ``getpass``/``print``/stdout, so the
whole dispatch is unit-testable by injecting a scripted IO.

Usage::

    keychainctl init
    keychainctl add default "work RDP" --attr host=pc --attr user=bob
    keychainctl search --attr host=pc
    keychainctl get <item-id> > secret.bin
    keychainctl ls
    keychainctl view          # read-only TUI
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from gest.core.keychain.errors import KeychainError
from gest.core.keychain.model import Item
from gest.core.keychain.vault import DEFAULT_VAULT_PATH, Vault


@dataclass
class CliIO:
    """The CLI's only contact with the terminal — injected so tests can script
    passphrases and capture output."""

    out: Callable[[str], None]
    err: Callable[[str], None]
    out_bytes: Callable[[bytes], None]
    ask_passphrase: Callable[[str], str]
    ask_secret: Callable[[str], str]


def _default_io() -> CliIO:
    import getpass

    return CliIO(
        out=print,
        err=lambda s: print(s, file=sys.stderr),
        out_bytes=lambda b: (sys.stdout.buffer.write(b), sys.stdout.buffer.flush()),
        ask_passphrase=getpass.getpass,
        ask_secret=getpass.getpass,
    )


# ---- helpers -----------------------------------------------------------
def parse_attrs(pairs: Sequence[str]) -> dict[str, str]:
    """Turn ``["k=v", ...]`` into a dict, raising ValueError on a bad token."""
    attrs: dict[str, str] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            raise ValueError(f"bad --attr {pair!r}; expected key=value")
        attrs[key] = value
    return attrs


def format_item_line(collection_id: str, item: Item) -> str:
    """One metadata line for an item — never its secret."""
    attrs = ",".join(f"{k}={v}" for k, v in sorted(item.attributes.items()))
    suffix = f"  [{attrs}]" if attrs else ""
    return f"{item.id}  {item.label}{suffix}"


def _open_unlocked(args, io: CliIO, vault_cls: type[Vault]) -> Vault | None:
    vault = vault_cls(args.vault)
    try:
        vault.unlock(io.ask_passphrase("Vault passphrase: "))
    except KeychainError as exc:
        io.err(str(exc))
        return None
    return vault


# ---- commands ----------------------------------------------------------
def cmd_init(args, io: CliIO, vault_cls: type[Vault]) -> int:
    first = io.ask_passphrase("New vault passphrase: ")
    if first != io.ask_passphrase("Confirm passphrase: "):
        io.err("passphrases do not match")
        return 1
    try:
        vault_cls.create(args.vault, first)
    except KeychainError as exc:
        io.err(str(exc))
        return 1
    io.out(f"created vault at {args.vault}")
    return 0


def cmd_add(args, io: CliIO, vault_cls: type[Vault]) -> int:
    try:
        attrs = parse_attrs(args.attr)
    except ValueError as exc:
        io.err(str(exc))
        return 2
    vault = _open_unlocked(args, io, vault_cls)
    if vault is None:
        return 1
    secret = sys.stdin.buffer.read() if args.secret_stdin else io.ask_secret("Secret: ").encode()
    try:
        item = vault.add_item(args.collection, args.label, attrs, secret)
        vault.save()
    except KeychainError as exc:
        io.err(str(exc))
        return 1
    io.out(item.id)
    return 0


def cmd_search(args, io: CliIO, vault_cls: type[Vault]) -> int:
    try:
        attrs = parse_attrs(args.attr)
    except ValueError as exc:
        io.err(str(exc))
        return 2
    vault = _open_unlocked(args, io, vault_cls)
    if vault is None:
        return 1
    hits = vault.search(attrs)
    for cid, item in hits:
        io.out(format_item_line(cid, item))
    return 0 if hits else 1


def cmd_get(args, io: CliIO, vault_cls: type[Vault]) -> int:
    try:
        attrs = parse_attrs(args.attr)
    except ValueError as exc:
        io.err(str(exc))
        return 2
    if bool(args.id) == bool(attrs):
        io.err("give exactly one of: an item id, or one/more --attr")
        return 2
    vault = _open_unlocked(args, io, vault_cls)
    if vault is None:
        return 1
    if args.id:
        found = vault.find_item(args.id)
        matches = [found] if found else []
    else:
        matches = vault.search(attrs)
    if not matches:
        io.err("no matching item")
        return 1
    if len(matches) > 1:
        io.err(f"{len(matches)} items match; narrow by id:")
        for _cid, item in matches:
            io.err(f"  {item.id}  {item.label}")
        return 1
    io.out_bytes(matches[0][1].secret)
    return 0


def cmd_ls(args, io: CliIO, vault_cls: type[Vault]) -> int:
    vault = _open_unlocked(args, io, vault_cls)
    if vault is None:
        return 1
    for col in vault.collections():
        alias = f" ({', '.join(col.aliases)})" if col.aliases else ""
        io.out(f"{col.label}{alias}  [{col.id}]  {len(col.items)} item(s)")
        for item in col.items.values():
            io.out(f"    {item.id}  {item.label}")
    return 0


def cmd_rm(args, io: CliIO, vault_cls: type[Vault]) -> int:
    vault = _open_unlocked(args, io, vault_cls)
    if vault is None:
        return 1
    found = vault.find_item(args.id)
    if not found:
        io.err("no such item")
        return 1
    vault.remove_item(found[0], args.id)
    vault.save()
    io.out(f"removed {args.id}")
    return 0


def cmd_mkcollection(args, io: CliIO, vault_cls: type[Vault]) -> int:
    vault = _open_unlocked(args, io, vault_cls)
    if vault is None:
        return 1
    col = vault.add_collection(args.label, aliases=args.alias or [])
    vault.save()
    io.out(col.id)
    return 0


def cmd_passwd(args, io: CliIO, vault_cls: type[Vault]) -> int:
    vault = _open_unlocked(args, io, vault_cls)
    if vault is None:
        return 1
    first = io.ask_passphrase("New passphrase: ")
    if first != io.ask_passphrase("Confirm passphrase: "):
        io.err("passphrases do not match")
        return 1
    vault.change_passphrase(first)
    io.out("passphrase changed")
    return 0


def cmd_view(args, io: CliIO, vault_cls: type[Vault]) -> int:
    vault = _open_unlocked(args, io, vault_cls)
    if vault is None:
        return 1
    from gest.tui.keychain.viewer import run_viewer

    run_viewer(vault)
    return 0


COMMANDS: dict[str, Callable[..., int]] = {
    "init": cmd_init,
    "add": cmd_add,
    "search": cmd_search,
    "get": cmd_get,
    "ls": cmd_ls,
    "rm": cmd_rm,
    "mkcollection": cmd_mkcollection,
    "passwd": cmd_passwd,
    "view": cmd_view,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="keychainctl",
        description="Inspect and edit a GeST/HeDE keychain vault (pre-daemon).",
    )
    parser.add_argument(
        "--vault", default=DEFAULT_VAULT_PATH, help="vault file (default: %(default)s)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create a new, empty vault")

    add = sub.add_parser("add", help="add an item to a collection")
    add.add_argument("collection", help="collection id or alias (e.g. default)")
    add.add_argument("label", help="human label for the item")
    add.add_argument("--attr", action="append", default=[], metavar="K=V",
                     help="a searchable attribute (repeatable)")
    add.add_argument("--secret-stdin", action="store_true",
                     help="read the raw secret from stdin instead of prompting")

    search = sub.add_parser("search", help="list items matching attributes (no secrets)")
    search.add_argument("--attr", action="append", default=[], metavar="K=V")

    get = sub.add_parser("get", help="write one item's secret to stdout")
    get.add_argument("id", nargs="?", help="item id")
    get.add_argument("--attr", action="append", default=[], metavar="K=V",
                     help="match by attributes instead of id (must be unique)")

    sub.add_parser("ls", help="list collections and items (no secrets)")

    rm = sub.add_parser("rm", help="remove an item by id")
    rm.add_argument("id")

    mk = sub.add_parser("mkcollection", help="create a collection")
    mk.add_argument("label")
    mk.add_argument("--alias", action="append", default=[])

    sub.add_parser("passwd", help="change the vault passphrase")
    sub.add_parser("view", help="browse the vault in a read-only TUI")
    return parser


def run(argv: Sequence[str] | None = None, *, io: CliIO | None = None,
        vault_cls: type[Vault] = Vault) -> int:
    args = build_parser().parse_args(argv)
    io = io or _default_io()
    try:
        return COMMANDS[args.command](args, io, vault_cls)
    except KeychainError as exc:  # any vault error the handlers didn't catch
        io.err(str(exc))
        return 1


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
