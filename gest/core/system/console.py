"""Read/list/validate the console keymap and font.

OpenRC keeps both as ``KEY="value"`` shell assignments: the keymap in
``/etc/conf.d/keymaps`` (``keymap="us"``) and the console font in
``/etc/conf.d/consolefont`` (``consolefont="ter-v16n"``). Reading and listing the
available choices is unprivileged; the backend does the privileged write, upserting
just the one key so any other settings in the file are preserved. Pure and
dependency-free, so it is unit-testable on CI.
"""

from __future__ import annotations

import os
import re

# keymap/font names: conservative — a letter/digit start, then letters, digits,
# dot, underscore, hyphen (us, de-latin1, ter-v16n, default8x16, lat9w-16).
_TOKEN_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]*\Z")

KEYMAPS_CONF = "/etc/conf.d/keymaps"
CONSOLEFONT_CONF = "/etc/conf.d/consolefont"
KEYMAPS_DIR = "/usr/share/keymaps"
CONSOLEFONTS_DIR = "/usr/share/consolefonts"

# Suffixes to strip from a data file to recover the bare name a user selects.
# Longest-first so ``.psf.gz`` wins over ``.gz``.
_KEYMAP_SUFFIXES = (".map.gz", ".kmap.gz", ".map", ".kmap")
_FONT_SUFFIXES = (".psfu.gz", ".psf.gz", ".fnt.gz", ".psfu", ".psf", ".fnt", ".gz")


def valid_keymap(name: str) -> bool:
    return bool(_TOKEN_RE.match(name)) and len(name) <= 64


def valid_font(name: str) -> bool:
    return bool(_TOKEN_RE.match(name)) and len(name) <= 64


# --- conf.d KEY="value" parse / upsert --------------------------------------

def _value_re(key: str) -> re.Pattern[str]:
    return re.compile(rf'^\s*{key}\s*=\s*"?([^"\n#]+?)"?\s*(?:#.*)?$', re.MULTILINE)


def parse_conf_value(text: str, key: str) -> str:
    """The value of ``key`` in an OpenRC conf.d file (or "" if unset)."""
    match = _value_re(key).search(text)
    return match.group(1).strip() if match else ""


def set_conf_value(text: str, key: str, value: str) -> str:
    """Upsert ``key="value"`` into a conf.d file, preserving every other line.

    Replaces the first existing ``key=`` assignment in place, or appends one if
    the key isn't present yet.
    """
    line = f'{key}="{value}"'
    pattern = re.compile(rf"^\s*{key}\s*=.*$", re.MULTILINE)
    if pattern.search(text):
        return pattern.sub(lambda _m: line, text, count=1)
    sep = "" if text == "" or text.endswith("\n") else "\n"
    return text + sep + line + "\n"


# --- current values ---------------------------------------------------------

def current_keymap(conf: str = KEYMAPS_CONF) -> str:
    try:
        with open(conf, encoding="utf-8") as fh:
            return parse_conf_value(fh.read(), "keymap")
    except OSError:
        return ""


def current_font(conf: str = CONSOLEFONT_CONF) -> str:
    try:
        with open(conf, encoding="utf-8") as fh:
            return parse_conf_value(fh.read(), "consolefont")
    except OSError:
        return ""


# --- listing available choices ----------------------------------------------

def _strip_suffix(name: str, suffixes: tuple[str, ...]) -> str:
    for suffix in suffixes:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _list_names(root: str, suffixes: tuple[str, ...], valid) -> list[str]:
    """Bare, de-duplicated, sorted names of the data files under ``root``."""
    names: set[str] = set()
    for _dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            name = _strip_suffix(filename, suffixes)
            if name and valid(name):
                names.add(name)
    return sorted(names)


def list_keymaps(root: str = KEYMAPS_DIR) -> list[str]:
    """Every console keymap under ``root`` (e.g. 'us', 'de-latin1'), sorted."""
    return _list_names(root, _KEYMAP_SUFFIXES, valid_keymap)


def list_fonts(root: str = CONSOLEFONTS_DIR) -> list[str]:
    """Every console font under ``root`` (e.g. 'ter-v16n', 'default8x16'), sorted."""
    return _list_names(root, _FONT_SUFFIXES, valid_font)
