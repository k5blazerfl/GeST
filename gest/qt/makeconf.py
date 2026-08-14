"""make.conf module logic: pure label/validation + a set bridge."""

from __future__ import annotations

from gest.core.makeconf.reader import Var, valid_name, valid_value
from gest.core.makeconf.writer import set_variable
from gest.qt.portageconf import apply_writes


def var_label(var: Var) -> str:
    return f"{var.name} = {var.value}"


def set_var(name: str, value: str) -> tuple[bool, str]:
    """Validate then apply a make.conf ``name=value`` assignment."""
    name = name.strip()
    if not valid_name(name):
        return (False, f"invalid variable name: {name!r}")
    if not valid_value(value):
        return (False, "value contains characters not allowed in make.conf")
    return apply_writes([set_variable(name, value)])
