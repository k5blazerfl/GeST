"""System capabilities → global ``USE`` tokens (the wizard's "Features" checklist).

The GeSI wizard surfaces a curated, human-readable list of *capabilities*
(Bluetooth, Printing, …) rather than raw Portage flags. Each capability maps to
one or more ``USE`` tokens that become the target's system-wide ``USE=`` policy
(the Handbook-endorsed "set it once, everywhere" layer — distinct from the
profile baseline below it and per-package surgery above it).

Pure data + a resolver, so "checklist → USE string" is unit-testable without a
TUI. A checked capability contributes its tokens; an *unchecked* capability whose
tokens the profile might otherwise enable contributes their negations (``-flag``)
so the choice is explicit either way. The wizard's System Role proposes a default
set (:func:`gest.core.install.assemble.propose`).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Capability:
    """One human-facing feature and the ``USE`` tokens it toggles."""

    key: str            # stable id stored in the selections (e.g. "bluetooth")
    label: str          # what the checklist shows ("Bluetooth")
    tokens: tuple[str, ...]   # USE tokens set when checked / negated when not


# Curated capability catalogue. Order = checklist order. Tokens verified against
# common desktop/server needs; media codecs are bundled behind one human choice.
CAPABILITIES: tuple[Capability, ...] = (
    Capability("bluetooth", "Bluetooth", ("bluetooth",)),
    Capability("printing", "Printing", ("cups",)),
    Capability("wifi", "Wi-Fi", ("networkmanager", "wifi")),
    Capability("audio", "Audio (PipeWire)", ("pipewire", "-pulseaudio")),
    Capability("wayland", "Wayland", ("wayland",)),
    Capability("a11y", "Accessibility", ("a11y",)),
    Capability("vaapi", "Hardware video acceleration", ("vaapi", "vdpau")),
    Capability("codecs", "Media codecs",
               ("x264", "x265", "vpx", "aom", "opus", "mp3", "aac", "flac",
                "vorbis", "theora")),
)

_BY_KEY = {c.key: c for c in CAPABILITIES}


def known_keys() -> frozenset[str]:
    """The set of valid capability keys."""
    return frozenset(_BY_KEY)


def resolve_global_use(enabled: frozenset[str] | set[str]) -> tuple[str, ...]:
    """Resolve a set of enabled capability keys to ordered ``USE`` tokens.

    Every capability in the catalogue contributes: its tokens verbatim when
    enabled, or each token negated (``flag`` -> ``-flag``, ``-flag`` -> ``flag``)
    when not. This makes the system-wide policy explicit in both directions —
    "Bluetooth off" writes ``-bluetooth``, not silence. Unknown keys raise so a
    bad selection can't slip a typo into make.conf.

    Order follows :data:`CAPABILITIES`, tokens within a capability in declared
    order, and each token appears once (first occurrence wins across overlaps).
    """
    unknown = set(enabled) - set(_BY_KEY)
    if unknown:
        raise ValueError(f"unknown capabilities: {sorted(unknown)}")
    out: list[str] = []
    seen: set[str] = set()
    for cap in CAPABILITIES:
        on = cap.key in enabled
        for tok in cap.tokens:
            rendered = tok if on else _negate(tok)
            base = rendered.lstrip("-")
            if base in seen:
                continue
            seen.add(base)
            out.append(rendered)
    return tuple(out)


def _negate(token: str) -> str:
    """``flag`` -> ``-flag`` and ``-flag`` -> ``flag`` (a capability declared with a
    leading ``-``, like ``-pulseaudio``, negates back to the positive when off)."""
    return token[1:] if token.startswith("-") else f"-{token}"
