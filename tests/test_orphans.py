"""Pure tests for repo-orphan assembly + report logic (no Portage).

Detection itself lives in ``reader.list_unavailable`` (Portage-backed, covered by
the live reader tests); here we inject a fake detector/size/deps to exercise the
pure assembly and the guardrail-facing report views.
"""

from gest.core.software import orphans
from gest.core.software.orphans import OrphanReport, RepoOrphan, scan_orphans


def _fake_detector():
    # (cp, version, world_member) — the shape reader.list_unavailable returns.
    return [
        ("media-sound/pyrrha", "0.4.69", True),    # @world, nothing needs it
        ("dev-libs/orphanlib", "1.0", False),      # a dep something still needs
    ]


_SIZES = {"media-sound/pyrrha": 5_000_000, "dev-libs/orphanlib": 200_000}
_DEPS = {"dev-libs/orphanlib": ["app-misc/thing"]}


def _scan():
    return scan_orphans(
        detector=_fake_detector,
        size_fn=lambda cp: _SIZES.get(cp, 0),
        deps_fn=lambda cp: _DEPS.get(cp, []),
    )


def test_scan_assembles_size_world_and_deps():
    report = _scan()
    by_cp = {o.cp: o for o in report.orphans}

    pyrrha = by_cp["media-sound/pyrrha"]
    assert pyrrha.version == "0.4.69"
    assert pyrrha.world_member is True
    assert pyrrha.size == 5_000_000
    assert pyrrha.required_by == []
    assert pyrrha.safe_to_unmerge is True
    assert pyrrha.cpv == "media-sound/pyrrha-0.4.69"
    assert pyrrha.category == "media-sound" and pyrrha.package == "pyrrha"

    lib = by_cp["dev-libs/orphanlib"]
    assert lib.world_member is False
    assert lib.required_by == ["app-misc/thing"]
    assert lib.safe_to_unmerge is False


def test_report_views():
    report = _scan()
    assert bool(report) is True
    assert report.total_size == 5_200_000
    assert [o.cp for o in report.world_members] == ["media-sound/pyrrha"]
    assert [o.cp for o in report.depended_on] == ["dev-libs/orphanlib"]


def test_empty_report_is_falsy():
    report = scan_orphans(detector=lambda: [], size_fn=lambda cp: 0,
                          deps_fn=lambda cp: [])
    assert not report
    assert report.total_size == 0
    assert "No unavailable packages" in orphans.format_report(report)


def test_format_report_flags_world_and_deps():
    text = orphans.format_report(_scan())
    assert "2 unavailable package(s)" in text
    assert "media-sound/pyrrha-0.4.69" in text
    assert "@world" in text
    assert "needed by 1" in text


def test_report_empty_default():
    assert not OrphanReport()
    assert OrphanReport().total_size == 0


def test_repo_orphan_cpv_without_version():
    assert RepoOrphan(cp="cat/pkg").cpv == "cat/pkg"
