"""Tests for the SSH deploy-key argv builders (pure / CI-safe)."""

from gest.core.repos import sshkey


def test_keygen_argv_is_passphraseless_ed25519():
    argv = sshkey.keygen_argv("/root/.ssh/id_ed25519", "gest-deploy@box")
    assert argv[0] == "ssh-keygen"
    assert "-t" in argv and argv[argv.index("-t") + 1] == "ed25519"
    # empty passphrase (-N "") so non-interactive syncs work
    assert argv[argv.index("-N") + 1] == ""
    assert argv[argv.index("-f") + 1] == "/root/.ssh/id_ed25519"
    assert argv[argv.index("-C") + 1] == "gest-deploy@box"


def test_keyscan_argv_targets_the_host():
    assert sshkey.keyscan_argv("github.com")[0] == "ssh-keyscan"
    assert sshkey.keyscan_argv("github.com")[-1] == "github.com"


def test_default_comment_uses_hostname_with_fallback():
    assert sshkey.default_comment("mybox") == "gest-deploy@mybox"
    assert sshkey.default_comment("") == "gest-deploy@gentoo"
    assert sshkey.default_comment("  ") == "gest-deploy@gentoo"


def test_paths_are_under_root_ssh():
    assert sshkey.KEY_PATH.startswith("/root/.ssh/")
    assert sshkey.PUB_PATH == sshkey.KEY_PATH + ".pub"
    assert sshkey.GITHUB_HOST == "github.com"
