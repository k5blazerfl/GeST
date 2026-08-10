"""CI-safe tests for the System Update planner — pure parsing of emerge output."""

from gest.core.software import update

_SAMPLE = """\
These are the packages that would be merged, in order:

Calculating dependencies  ... done!

[ebuild   R    ] app-arch/gzip-1.14::gentoo  USE="-pic -static" 0 KiB
[ebuild     U  ] app-crypt/libsecret-0.21.7::gentoo [0.21.6]  USE="crypt" 1,024 KiB
[ebuild  N     ] dev-libs/newdep-2.0::gentoo  USE="foo -bar" 512 KiB
[binary     U  ] sys-apps/foo-3.1::gentoo [3.0]  USE="x" 2.5 MiB

Total: 4 packages (2 upgrades, 1 new, 1 reinstall), Size of downloads: 4,096 KiB
"""


def test_parse_changes_actions_versions_and_size():
    changes = {c.cp: c for c in update.parse_changes(_SAMPLE)}
    assert set(changes) == {"app-arch/gzip", "app-crypt/libsecret",
                            "dev-libs/newdep", "sys-apps/foo"}
    assert changes["app-arch/gzip"].action == update.REBUILD
    assert changes["app-crypt/libsecret"].action == update.UPDATE
    assert changes["app-crypt/libsecret"].old_version == "0.21.6"
    assert changes["app-crypt/libsecret"].new_version == "0.21.7"
    assert changes["dev-libs/newdep"].action == update.NEW
    assert changes["sys-apps/foo"].binary is True
    assert changes["sys-apps/foo"].size == int(2.5 * 1024 ** 2)
    assert changes["app-crypt/libsecret"].category == "app-crypt"
    assert changes["app-crypt/libsecret"].package == "libsecret"


def test_parse_changes_ignores_noise():
    assert update.parse_changes("Calculating dependencies ... done!") == []
    assert update.parse_changes("Total: 0 packages") == []


def test_split_cpv():
    assert update.split_cpv("app-arch/gzip-1.14") == ("app-arch/gzip", "1.14")
    assert update.split_cpv("sys-libs/db-1.0.35-r1") == ("sys-libs/db", "1.0.35-r1")
    assert update.split_cpv("media-libs/x264-0.0.20220222") == (
        "media-libs/x264", "0.0.20220222")


def test_plan_update_counts_and_total():
    plan = update.UpdatePlan(changes=update.parse_changes(_SAMPLE))
    assert plan.counts() == {"new": 1, "update": 2, "rebuild": 1}
    assert plan.total_download == 4096 * 1024      # matches the Total line


def test_plan_update_wires_runner_and_reports_error():
    ok = update.plan_update(runner=lambda _argv: (0, _SAMPLE))
    assert ok.ok and len(ok.changes) == 4
    bad = update.plan_update(runner=lambda _argv: (1, "!!! circular dependencies\n"))
    assert not bad.ok and "circular" in bad.error


def test_human_size():
    assert update.human_size(0) == "—"
    assert update.human_size(1024 ** 2) == "1.0 MiB"


def test_parse_merge_progress():
    p = update.parse_merge_progress(
        ">>> Emerging (2 of 5) app-editors/vim-9.1::gentoo")
    assert (p.phase, p.n, p.total, p.atom) == ("Emerging", 2, 5, "app-editors/vim-9.1")
    q = update.parse_merge_progress(
        ">>> Installing (2 of 5) app-editors/vim-9.1::gentoo")
    assert q.phase == "Installing"
    assert update.parse_merge_progress(">>> Emerging binary (3 of 5) x/y-1.0").phase \
        == "Emerging"
    assert update.parse_merge_progress("Calculating dependencies ... done!") is None
