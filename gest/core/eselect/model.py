"""Data types for the eselect module."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Module:
    name: str
    description: str = ""


@dataclass(slots=True)
class Target:
    number: int
    name: str
    current: bool = False
