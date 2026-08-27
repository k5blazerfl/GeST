"""CI-safe tests for kernel build: argv builders, source-tree reader parsing,
the build pipeline, and the direct apply path via FakeExecutor."""

import asyncio

import pytest

from gest.core.exec.executor import FakeExecutor
from gest.core.exec.steps import StepError
from gest.core.kernel import build, commands, reader

# --- argv builders ----------------------------------------------------------

def test_genkernel_argv_default_and_config():
    assert commands.genkernel_argv() == ["genkernel", "all"]
    assert commands.genkernel_argv(kernel_config="/etc/kernels/config") == [
        "genkernel", "--kernel-config=/etc/kernels/config", "all"]


def test_make_argv_targets_and_jobs():
    assert commands.make_argv(jobs=8, directory="/usr/src/linux") == [
        "make", "-C", "/usr/src/linux", "-j8"]
    assert commands.make_argv("modules_install", jobs=4) == [
        "make", "-C", "/usr/src/linux", "-j4", "modules_install"]


def test_genkernel_argv_plymouth_bakes_hede_splash():
    assert commands.genkernel_argv(plymouth=True) == [
        "genkernel", "--plymouth", "--plymouth-theme=hede", "all"]
    # config + plymouth together, in a sane order (flags before the `all` target).
    assert commands.genkernel_argv(kernel_config="/etc/kernels/config", plymouth=True) == [
        "genkernel", "--kernel-config=/etc/kernels/config",
        "--plymouth", "--plymouth-theme=hede", "all"]


def test_genkernel_argv_initramfs_action():
    # The re-tint path rebuilds only the initramfs (no kernel recompile).
    assert commands.genkernel_argv(plymouth=True, action="initramfs") == [
        "genkernel", "--plymouth", "--plymouth-theme=hede", "initramfs"]
    with pytest.raises(ValueError):
        commands.genkernel_argv(action="oldconfig")


def test_dracut_argv():
    assert commands.dracut_argv() == ["dracut", "--force"]
    assert commands.dracut_argv("6.6.30-gentoo") == ["dracut", "--force", "--kver", "6.6.30-gentoo"]


def test_dracut_argv_plymouth_adds_module():
    assert commands.dracut_argv(plymouth=True) == ["dracut", "--force", "--add", "plymouth"]
    assert commands.dracut_argv("6.6.30-gentoo", plymouth=True) == [
        "dracut", "--force", "--add", "plymouth", "--kver", "6.6.30-gentoo"]


@pytest.mark.parametrize("call", [
    lambda: commands.make_argv("oldconfig"),                       # bad target
    lambda: commands.make_argv(jobs=0),                            # jobs out of range
    lambda: commands.make_argv(directory="relative"),             # not absolute
    lambda: commands.make_argv(directory="/usr/../etc"),          # traversal
    lambda: commands.genkernel_argv(kernel_config="rel"),         # not absolute
    lambda: commands.dracut_argv("bad ver"),                       # bad kver
])
def test_builders_reject_bad_input(call):
    with pytest.raises(ValueError):
        call()


# --- reader parsing ---------------------------------------------------------

def test_parse_sources_filters_and_sorts():
    names = ["linux-6.6.30-gentoo", "README", "linux-6.1.0-gentoo", "distfiles"]
    assert reader.parse_sources(names) == ["linux-6.6.30-gentoo", "linux-6.1.0-gentoo"]


# --- pipeline ---------------------------------------------------------------

def test_build_steps_genkernel_is_one_command():
    steps = build.build_steps(build.BuildConfig(method="genkernel"))
    assert [s.label for s in steps] == ["genkernel all"]


def test_build_steps_make_full_pipeline():
    cfg = build.BuildConfig(method="make", jobs=4, initramfs=True)
    labels = [s.label for s in build.build_steps(cfg)]
    assert labels == ["build kernel", "install modules", "install kernel", "build initramfs"]


def test_build_steps_make_jobs_zero_uses_all_cpus(monkeypatch):
    # jobs=0 means "auto" → every detected CPU, NOT a silent -j1 (regression: a
    # single-threaded kernel compile that never spins the fans up).
    monkeypatch.setattr(build.reader, "cpu_count", lambda: 12)
    steps = build.build_steps(build.BuildConfig(method="make", jobs=0))
    assert steps[0].argv == ["make", "-C", "/usr/src/linux", "-j12"]


def test_build_steps_make_jobs_zero_clamps_to_max(monkeypatch):
    monkeypatch.setattr(build.reader, "cpu_count", lambda: commands.MAX_JOBS + 99)
    steps = build.build_steps(build.BuildConfig(method="make", jobs=0))
    assert steps[0].argv[-1] == f"-j{commands.MAX_JOBS}"


def test_build_steps_genkernel_plymouth_flows_to_argv():
    steps = build.build_steps(build.BuildConfig(method="genkernel", plymouth=True))
    assert steps[0].argv == ["genkernel", "--plymouth", "--plymouth-theme=hede", "all"]


def test_build_steps_make_plymouth_adds_dracut_module():
    cfg = build.BuildConfig(method="make", jobs=4, initramfs=True, plymouth=True)
    initramfs = build.build_steps(cfg)[-1]
    assert initramfs.label == "build initramfs"
    assert initramfs.argv == ["dracut", "--force", "--add", "plymouth"]


def test_build_steps_no_plymouth_by_default():
    genk = build.build_steps(build.BuildConfig(method="genkernel"))[0]
    assert "--plymouth" not in genk.argv
    dracut = build.build_steps(build.BuildConfig(method="make", jobs=1))[-1]
    assert "--add" not in dracut.argv


def test_build_steps_make_without_initramfs():
    cfg = build.BuildConfig(method="make", jobs=2, initramfs=False)
    assert [s.label for s in build.build_steps(cfg)] == [
        "build kernel", "install modules", "install kernel"]


def test_build_steps_rejects_unknown_method():
    with pytest.raises(ValueError):
        build.build_steps(build.BuildConfig(method="bzImage"))


# --- direct apply -----------------------------------------------------------

def test_build_direct_runs_make_pipeline_in_order():
    ex = FakeExecutor()
    cfg = build.BuildConfig(method="make", jobs=2, initramfs=True)
    seen: list[int] = []
    asyncio.run(build.build(cfg, ex, on_step=seen.append))
    assert [c[0] for c in ex.calls] == ["make", "make", "make", "dracut"]
    assert seen == [0, 1, 2, 3]


def test_build_direct_stops_at_first_failure():
    ex = FakeExecutor(code_for=lambda argv: 1 if argv[-1] == "modules_install" else 0)
    with pytest.raises(StepError):
        asyncio.run(build.build(build.BuildConfig(method="make", jobs=1), ex))
    # build kernel ran, modules_install failed, install/dracut never ran.
    assert [c[-1] for c in ex.calls] == ["-j1", "modules_install"]
