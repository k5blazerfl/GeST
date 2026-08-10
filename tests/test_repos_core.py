"""CI-safe tests for the repositories core (repos.conf parse + argv builders)."""

import pytest

from gest.core.repos import commands, reader, refresh, writer

_CONF_MAIN = (
    "[DEFAULT]\nmain-repo = gentoo\n\n"
    "[gentoo]\nlocation = /var/db/repos/gentoo\nsync-type = rsync\n"
    "sync-uri = rsync://r/gentoo\n"
)
_CONF_OVL = (
    "# created by eselect-repo\n"
    "[amphitheater]\nlocation = /var/db/repos/amphitheater\nsync-type = git\n"
    "sync-uri = https://github.com/k5blazerfl/Amphitheater.git\n"
)


def test_enabled_repos_merges_fragments_and_reads_main(tmp_path):
    # main-repo comes from [DEFAULT] in one fragment; the overlay from another.
    (tmp_path / "gentoo.conf").write_text(_CONF_MAIN)
    (tmp_path / "eselect-repo.conf").write_text(_CONF_OVL)
    repos = reader.enabled_repos(str(tmp_path))
    by = {r.name: r for r in repos}
    assert repos[0].name == "gentoo" and repos[0].main       # main sorts first
    assert by["gentoo"].sync_uri == "rsync://r/gentoo"
    assert by["amphitheater"].sync_type == "git"
    assert by["amphitheater"].sync_uri.endswith("Amphitheater.git")
    assert not by["amphitheater"].main


def test_enabled_repos_missing_dir_is_empty(tmp_path):
    assert reader.enabled_repos(str(tmp_path / "nope")) == []


def test_command_builders():
    assert commands.enable_argv("guru")[-2:] == ["enable", "guru"]
    assert commands.disable_argv("x") == ["eselect", "repository", "disable", "-f", "x"]
    assert commands.remove_argv("x")[-3:] == ["remove", "-f", "x"]
    assert commands.add_argv("mine", "git", "https://h/r")[-3:] == ["mine", "git", "https://h/r"]


@pytest.mark.parametrize("name", ["", "a b", "bad/name", "-lead"])
def test_invalid_names(name):
    with pytest.raises(ValueError):
        commands.enable_argv(name)


def test_add_validates_type_and_uri():
    with pytest.raises(ValueError):
        commands.add_argv("r", "Git", "https://h/r")     # bad type
    with pytest.raises(ValueError):
        commands.add_argv("r", "git", "has space")       # bad uri


# -- refresh-on-open state (GeST-owned list file) ----------------------------

def test_refresh_parse_ignores_blanks_and_comments():
    text = "# my repos\nguru\n\n  amphitheater  \n"
    assert refresh.parse(text) == {"guru", "amphitheater"}


def test_refresh_render_is_sorted_and_empty_deletes():
    assert refresh.render({"guru", "amphitheater"}) == "amphitheater\nguru\n"
    assert refresh.render(set()) == ""                 # -> ConfigWrite deletes


def test_refresh_toggle_round_trips():
    names = refresh.toggle(set(), "guru", True)
    assert names == {"guru"}
    assert refresh.toggle(names, "guru", False) == set()
    assert refresh.render(refresh.parse("guru\n")) == "guru\n"


def test_reader_cross_references_state_file(tmp_path):
    repos_conf = tmp_path / "repos.conf"
    repos_conf.mkdir()
    (repos_conf / "gentoo.conf").write_text(_CONF_MAIN)
    (repos_conf / "eselect-repo.conf").write_text(_CONF_OVL)
    (tmp_path / "gest").mkdir()
    (tmp_path / "gest" / "refresh").write_text("amphitheater\n")
    by = {r.name: r for r in reader.enabled_repos(str(repos_conf))}
    assert by["amphitheater"].refresh is True
    assert by["gentoo"].refresh is False


def test_reader_no_state_file_means_no_refresh(tmp_path):
    repos_conf = tmp_path / "repos.conf"
    repos_conf.mkdir()
    (repos_conf / "eselect-repo.conf").write_text(_CONF_OVL)
    by = {r.name: r for r in reader.enabled_repos(str(repos_conf))}
    assert by["amphitheater"].refresh is False


def test_writer_builds_state_file_write(tmp_path):
    target = tmp_path / "gest" / "refresh"
    write = writer.set_refresh({"guru", "amphitheater"}, path=str(target))
    assert write.path == str(target)
    assert refresh.parse(write.text) == {"guru", "amphitheater"}
    assert writer.set_refresh(set(), path=str(target)).text == ""  # deletes
