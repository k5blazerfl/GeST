"""Turn a kernel-build request into an ordered pipeline, and run it.

`BuildConfig` picks the method; `build_steps` produces the ordered `Step`s. The
genkernel method is a single command (config + compile + initramfs + install);
the make method is build → modules_install → install, then an optional dracut
initramfs. `build_steps` is the single source of truth for the pipeline — the
direct path runs it via `run_steps`, and the streaming `Kernel` backend runs the
same argv on an installed system.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from gest.core.exec.executor import Executor
from gest.core.exec.runner import OnProgress
from gest.core.exec.steps import Step, run_steps
from gest.core.kernel import commands, reader


@dataclass(slots=True, frozen=True)
class BuildConfig:
    """A kernel-build request. ``jobs`` 0 means "use every detected CPU" (see
    ``reader.cpu_count``); a positive value pins the job count explicitly."""

    method: str                      # "genkernel" | "make"
    source_dir: str = "/usr/src/linux"
    jobs: int = 0
    kernel_config: str = ""          # genkernel --kernel-config
    initramfs: bool = True           # make path: run dracut afterwards
    kver: str = ""                   # dracut --kver (make path)
    plymouth: bool = False           # bake the HeDE Plymouth splash into the initramfs


def build_steps(config: BuildConfig) -> list[Step]:
    """The ordered pipeline for ``config`` (raises ValueError on bad inputs)."""
    if config.method == "genkernel":
        return [Step("genkernel all",
                     commands.genkernel_argv(kernel_config=config.kernel_config,
                                             plymouth=config.plymouth))]
    if config.method != "make":
        raise ValueError(f"unknown build method: {config.method!r}")
    jobs = config.jobs if config.jobs > 0 else min(reader.cpu_count(), commands.MAX_JOBS)
    steps = [
        Step("build kernel", commands.make_argv(jobs=jobs, directory=config.source_dir)),
        Step("install modules",
             commands.make_argv("modules_install", jobs=jobs, directory=config.source_dir)),
        Step("install kernel",
             commands.make_argv("install", jobs=jobs, directory=config.source_dir)),
    ]
    if config.initramfs:
        steps.append(Step("build initramfs",
                          commands.dracut_argv(config.kver, plymouth=config.plymouth)))
    return steps


async def build(
    config: BuildConfig,
    executor: Executor,
    *,
    on_progress: OnProgress | None = None,
    on_step: Callable[[int], None] | None = None,
) -> None:
    """Run the build directly through ``executor`` (root/live-CD path)."""
    await run_steps(build_steps(config), executor, on_progress=on_progress, on_step=on_step)
