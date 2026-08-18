"""Validate a ``helm.recipe`` before it is materialized or installed.

Pure structural checks + reference resolution: bad runner/arch, programs without
an exe, unknown step actions, files missing a source, and ``extract`` steps that
name a file id no ``files`` entry provides. Returns a list of :class:`Issue`;
``error`` means "don't run this", ``warning`` means "probably wrong, but usable".
"""

from __future__ import annotations

from dataclasses import dataclass

from gest.core.drydock import recipe as R
from gest.core.drydock.model import ARCHES, RUNNERS

ERROR = "error"
WARNING = "warning"

VALID_ACTIONS = frozenset({
    R.ACTION_EXTRACT, R.ACTION_MOVE, R.ACTION_COPY, R.ACTION_CHMODX,
    R.ACTION_EXECUTE, R.ACTION_WRITE_FILE, R.ACTION_WRITE_CONFIG, R.ACTION_WRITE_JSON,
    R.ACTION_CREATE_PREFIX, R.ACTION_WINEEXEC, R.ACTION_WINETRICKS,
    R.ACTION_REGEDIT, R.ACTION_REGEDIT_FILE, R.ACTION_REGDELETE,
    R.ACTION_WINEKILL, R.ACTION_EJECT_DISC, R.ACTION_MANUAL,
})


@dataclass(slots=True)
class Issue:
    level: str
    message: str


def lint(recipe: R.Recipe) -> list[Issue]:
    issues: list[Issue] = []

    if not recipe.app_name:
        issues.append(Issue(ERROR, "app.name is empty"))
    if recipe.bottle.runner not in RUNNERS:
        issues.append(Issue(ERROR, f"bottle.runner {recipe.bottle.runner!r} is not one of "
                                   f"{sorted(RUNNERS)}"))
    if recipe.bottle.arch not in ARCHES:
        issues.append(Issue(ERROR, f"bottle.arch {recipe.bottle.arch!r} is not one of "
                                   f"{sorted(ARCHES)}"))

    file_ids: set[str] = set()
    for entry in recipe.files:
        if not entry.id:
            issues.append(Issue(ERROR, "a files entry has no id"))
        file_ids.add(entry.id)
        if not entry.url and not entry.user_provided:
            issues.append(Issue(WARNING, f"file {entry.id!r} has neither a url nor a "
                                         "user_provided prompt"))

    if not recipe.programs:
        issues.append(Issue(WARNING, "recipe exposes no programs (nothing to launch)"))
    for index, program in enumerate(recipe.programs):
        if not program.exe:
            issues.append(Issue(ERROR, f"program {program.name or index!r} has no exe"))

    for number, step in enumerate(recipe.steps, 1):
        if step.action not in VALID_ACTIONS:
            issues.append(Issue(ERROR, f"step {number}: unknown action {step.action!r}"))
        elif step.action == R.ACTION_MANUAL:
            original = step.params.get("original", "")
            issues.append(Issue(WARNING, f"step {number}: manual step needs a human"
                                         + (f" ({original})" if original else "")))
        if step.action == R.ACTION_EXTRACT:
            ref = str(step.params.get("file", ""))
            # a bare identifier (not a path or variable) must name a declared file.
            if ref and "/" not in ref and not ref.startswith("$") and ref not in file_ids:
                issues.append(Issue(WARNING, f"step {number}: extract references file "
                                             f"{ref!r}, which no files entry provides"))

    return issues


def has_errors(issues: list[Issue]) -> bool:
    return any(issue.level == ERROR for issue in issues)
