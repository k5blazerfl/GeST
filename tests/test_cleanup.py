"""CI-safe tests for the Clean Up (depclean) planner — pure parsing + sizing."""

from gest.core.software import cleanup

_SAMPLE = """\
 * Always study the list of packages to be cleaned ...
Calculating dependencies  ... done!
>>> Calculating removal order...

>>> These are the packages that would be unmerged:

 app-arch/innoextract
    selected: 1.10_pre20250206-r1
   protected: none
     omitted: none

 dev-libs/oldlib
    selected: 1.4.2
   protected: none
     omitted: none

All selected packages: =app-arch/innoextract-1.10_pre20250206-r1 =dev-libs/oldlib-1.4.2

>>> 'Selected' packages are slated for removal.

Packages installed:   1200
Packages in world:    53
Packages in system:   50
Required packages:    1198
Number to remove:     2
"""


def test_parse_orphans_extracts_cp_and_version():
    orphans = cleanup.parse_orphans(_SAMPLE)
    assert [(o.cp, o.version) for o in orphans] == [
        ("app-arch/innoextract", "1.10_pre20250206-r1"),
        ("dev-libs/oldlib", "1.4.2"),
    ]
    assert orphans[0].category == "app-arch"
    assert orphans[0].package == "innoextract"


def test_parse_orphans_ignores_noise_and_stops_at_summary():
    # No "pulled in by" / warning / summary lines leak into the orphan list.
    orphans = cleanup.parse_orphans(_SAMPLE)
    assert len(orphans) == 2
    assert cleanup.parse_orphans("nothing to unmerge here") == []


def test_parse_counts():
    counts = cleanup.parse_counts(_SAMPLE)
    assert counts == {"installed": 1200, "world": 53, "system": 50,
                      "required": 1198, "to_remove": 2}


def test_installed_size_reads_vdb(tmp_path):
    pkgdir = tmp_path / "app-arch" / "innoextract-1.10_pre20250206-r1"
    pkgdir.mkdir(parents=True)
    (pkgdir / "SIZE").write_text("1010380\n")
    o = cleanup.Orphan("app-arch/innoextract", "1.10_pre20250206-r1")
    assert cleanup.installed_size(o, vdb=str(tmp_path)) == 1010380
    # missing SIZE / unknown version -> 0, never raises
    assert cleanup.installed_size(cleanup.Orphan("x/y", "9"), vdb=str(tmp_path)) == 0
    assert cleanup.installed_size(cleanup.Orphan("x/y")) == 0


def test_plan_cleanup_wires_runner_and_sizes(tmp_path):
    for cp, ver, size in [("app-arch/innoextract", "1.10_pre20250206-r1", "1010380"),
                          ("dev-libs/oldlib", "1.4.2", "500")]:
        cat, pkg = cp.split("/")
        d = tmp_path / cat / f"{pkg}-{ver}"
        d.mkdir(parents=True)
        (d / "SIZE").write_text(size)
    plan = cleanup.plan_cleanup(runner=lambda _argv: (0, _SAMPLE), vdb=str(tmp_path))
    assert plan.ok
    assert [o.cp for o in plan.orphans] == ["app-arch/innoextract", "dev-libs/oldlib"]
    assert plan.total_size == 1010880
    assert plan.counts["to_remove"] == 2


def test_plan_cleanup_reports_resolution_error():
    err = "!!! Error: circular dependencies\n"
    plan = cleanup.plan_cleanup(runner=lambda _argv: (1, err))
    assert not plan.ok
    assert "circular dependencies" in plan.error
    assert plan.orphans == []


def test_human_size():
    assert cleanup.human_size(0) == "—"
    assert cleanup.human_size(1010380) == "986.7 KiB"
    assert cleanup.human_size(512).endswith("B")
