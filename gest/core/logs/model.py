"""Data model for the system logs module."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class LogSource:
    key: str
    label: str
    kind: str          # "command" (e.g. dmesg) | "file"
    path: str = ""     # filesystem path for file sources
