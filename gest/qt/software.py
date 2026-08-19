"""Software module logic: pure labels/formatters + sync bridges to the async,
polkit-gated Software backend (search results, @world, cleanup, news)."""

from __future__ import annotations

from gest.core.software.model import SearchResult
from gest.qt.backend import run_backend


def search_result_label(result: SearchResult) -> str:
    """One row: 'category/package  best-version  ✓' (✓ = installed)."""
    mark = "  ✓" if result.installed else ""
    version = f"  {result.best_version}" if result.best_version else ""
    return f"{result.cp}{version}{mark}"


# --- pure preview formatters (the streamed ops show these before running) ------

def format_update_plan(plan) -> str:
    """A text summary of an ``emerge -uDN @world --pretend`` plan."""
    if not plan.ok:
        return plan.error or "Could not compute an update plan."
    if not plan.changes:
        return "@world is up to date."
    lines = []
    for change in plan.changes:
        arrow = (f"{change.old_version} → {change.new_version}"
                 if change.old_version else change.new_version)
        lines.append(f"{change.action:7} {change.cp}  {arrow}")
    counts = ", ".join(f"{v} {k}" for k, v in sorted(plan.counts().items()))
    lines += ["", f"{len(plan.changes)} change(s): {counts}"]
    return "\n".join(lines)


def format_cleanup_plan(plan) -> str:
    """A text summary of an ``emerge --depclean --pretend`` plan."""
    from gest.core.software.cleanup import human_size

    if not plan.ok:
        return plan.error or "Could not compute a cleanup plan."
    if not plan.orphans:
        return "Nothing to clean up."
    lines = [f"{o.cp}-{o.version}  {human_size(o.size)}" for o in plan.orphans]
    lines += ["",
              f"{len(plan.orphans)} package(s), {human_size(plan.total_size)} reclaimable"]
    return "\n".join(lines)


def news_item_label(item) -> str:
    """One news-list row: an unread dot, the date, and the title."""
    return f"{'●' if item.unread else ' '} {item.date}  {item.title}"


def format_news_content(content) -> str:
    """Render a parsed news item (header block + body) as plain text."""
    head = "\n".join(f"{label}: {value}" for label, value in content.headers)
    body = "\n".join(content.body)
    return f"{head}\n\n{body}" if head else body


# --- sync bridges to the polkit-gated backend ----------------------------------

def package_status() -> tuple[bool, str]:
    """(busy, human_label) for the shared package backend — the busy gate the
    mutating modules check before starting. Unreachable backend → not busy."""
    async def run():
        from gest.core.software.backend_client import SoftwareBackend

        backend = await SoftwareBackend().connect()
        try:
            return await backend.package_status()
        finally:
            await backend.close()

    ok, msg = run_backend(run)
    # run_backend maps a clean tuple through; on a connect error it returns
    # (False, err) which is exactly "not busy" for our purposes.
    return ok, msg


def deselect(atoms: list[str]) -> tuple[bool, str]:
    """Drop atoms from @world (does not unmerge)."""
    async def run():
        from gest.core.software.backend_client import SoftwareBackend

        backend = await SoftwareBackend().connect()
        try:
            return await backend.deselect(atoms)
        finally:
            await backend.close()

    return run_backend(run)


def unmerge(atoms: list[str]) -> tuple[bool, str]:
    """Forcibly remove atoms (emerge --unmerge) and wait for completion.

    Drives the streamed backend op to its Finished signal, collecting the emerge
    log, and returns ``(ok, output)``. Blocking — the caller must confirm first
    (this bypasses depclean's dependency safety net). A future refinement could
    stream the log live via the OperationModule path; for the handful of small
    packages a repo-orphan cleanup touches, running to completion is fine.
    """
    import asyncio

    async def run():
        from gest.core.software.backend_client import SoftwareBackend

        backend = await SoftwareBackend().connect()
        lines: list[str] = []
        done = asyncio.get_running_loop().create_future()

        def on_progress(batch: list[str]) -> None:
            lines.extend(batch)

        def on_finished(code: int) -> None:
            if not done.done():
                done.set_result(code)

        try:
            await backend.unmerge_multi(atoms, on_progress=on_progress,
                                        on_finished=on_finished)
            code = await done
            tail = "\n".join(lines[-20:])
            return [code == 0, tail if code == 0 else f"emerge exited {code}\n{tail}"]
        finally:
            await backend.close()

    return run_backend(run)


def _mark_news(selector: str, read: bool) -> tuple[bool, str]:
    async def run():
        from gest.core.software.backend_client import SoftwareBackend

        backend = await SoftwareBackend().connect()
        try:
            method = backend.mark_news_read if read else backend.mark_news_unread
            ok = await method(selector)
            # the backend returns a bare bool; wrap it so run_backend can't read
            # a False as success.
            return [bool(ok), "" if ok else "the backend rejected the change"]
        finally:
            await backend.close()

    return run_backend(run)


def mark_news_read(selector: str) -> tuple[bool, str]:
    return _mark_news(selector, True)


def mark_news_unread(selector: str) -> tuple[bool, str]:
    return _mark_news(selector, False)
