"""``repos.conf`` / ``binrepos.conf`` INI grammar: parse and clean render.

``[section]`` headers with ``key = value`` entries and an optional ``[DEFAULT]``
block. Section order is preserved on parse. :func:`render` is a *clean*
generator used for files GeST fully owns (e.g. ``binrepos.conf/gest.conf``);
``repos.conf`` is only ever *read* through this codec — its mutations go through
``eselect repository``, which owns that file's formatting.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_SECTION = "DEFAULT"


@dataclass(slots=True)
class Section:
    name: str
    entries: dict[str, str] = field(default_factory=dict)


def parse(text: str) -> tuple[dict[str, str], list[Section]]:
    """Parse INI text into ``(default_entries, sections)``.

    ``default_entries`` holds the ``[DEFAULT]`` block (``{}`` if absent);
    ``sections`` are the remaining sections in first-seen order. Comment lines
    (``#`` or ``;``) and blank lines are ignored.
    """
    defaults: dict[str, str] = {}
    sections: list[Section] = []
    by_name: dict[str, Section] = {}
    current: dict[str, str] | None = None
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith(";"):
            continue
        if s.startswith("[") and s.endswith("]"):
            name = s[1:-1].strip()
            if name.upper() == DEFAULT_SECTION:
                current = defaults
            elif name in by_name:
                current = by_name[name].entries
            else:
                sect = Section(name)
                sections.append(sect)
                by_name[name] = sect
                current = sect.entries
            continue
        if current is not None and "=" in line:
            key, _, value = line.partition("=")
            current[key.strip()] = value.strip()
    return defaults, sections


def sections_dict(text: str) -> dict[str, dict[str, str]]:
    """Convenience: ``{section_name: {key: value}}`` (excludes ``[DEFAULT]``)."""
    _defaults, sections = parse(text)
    return {sect.name: sect.entries for sect in sections}


def render(sections: list[Section], defaults: dict[str, str] | None = None) -> str:
    """Render sections to INI text (clean, for GeST-owned files).

    A ``[DEFAULT]`` block is emitted first when ``defaults`` is non-empty.
    """
    blocks: list[str] = []
    if defaults:
        blocks.append(_render_block(DEFAULT_SECTION, defaults))
    for sect in sections:
        blocks.append(_render_block(sect.name, sect.entries))
    text = "\n\n".join(blocks).strip()
    return text + "\n" if text else ""


def _render_block(name: str, entries: dict[str, str]) -> str:
    lines = [f"[{name}]"]
    lines += [f"{key} = {value}" for key, value in entries.items()]
    return "\n".join(lines)
