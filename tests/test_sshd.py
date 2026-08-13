"""CI-safe tests for the sshd config core: parsing (defaults + active-over-
commented), upsert (replace first active line, preserve the rest, append absent),
validators, argv, and the reader."""

from gest.core.sshd import commands, config, reader
from gest.core.sshd.model import DEFAULTS, SshdSettings

# --- parsing ----------------------------------------------------------------

def test_empty_config_yields_openssh_defaults():
    assert config.parse_settings("") == DEFAULTS


def test_parse_reads_active_value_not_the_commented_one():
    text = "#Port 22\nPort 2222\nPermitRootLogin no\nX11Forwarding yes\n"
    s = config.parse_settings(text)
    assert s.port == 2222
    assert s.permit_root_login == "no"
    assert s.x11_forwarding is True
    # unspecified directives fall back to defaults
    assert s.password_authentication == DEFAULTS.password_authentication
    assert s.pubkey_authentication is True


def test_parse_first_active_wins():
    text = "PasswordAuthentication no\nPasswordAuthentication yes\n"
    assert config.parse_settings(text).password_authentication is False


# --- validation -------------------------------------------------------------

def test_validators():
    assert config.valid_port(22) and config.valid_port(65535)
    assert not config.valid_port(0) and not config.valid_port(70000)
    assert not config.valid_port(True)
    assert config.valid_root_login("prohibit-password")
    assert not config.valid_root_login("maybe")
    assert config.valid_settings(SshdSettings())
    assert not config.valid_settings(SshdSettings(port=0))
    assert not config.valid_settings(SshdSettings(permit_root_login="bogus"))


# --- upsert -----------------------------------------------------------------

def test_apply_replaces_first_active_line_and_preserves_others():
    text = "# header comment\n#Port 22\nPort 2222\nBanner /etc/issue\n"
    out = config.apply_settings(text, SshdSettings(port=22))
    assert "Port 22\n" in out
    assert "#Port 22\n" in out                 # commented line untouched
    assert "# header comment\n" in out
    assert "Banner /etc/issue\n" in out        # unrelated directive kept
    assert out.count("\nPort 2222") == 0       # the old active value is gone


def test_apply_appends_absent_directives():
    out = config.apply_settings("", SshdSettings(
        port=22, permit_root_login="no", password_authentication=False,
        pubkey_authentication=True, x11_forwarding=False, permit_empty_passwords=False))
    assert "Port 22" in out
    assert "PermitRootLogin no" in out
    assert "PasswordAuthentication no" in out
    assert "PubkeyAuthentication yes" in out
    assert "X11Forwarding no" in out
    assert "PermitEmptyPasswords no" in out


def test_apply_round_trips_through_parse():
    settings = SshdSettings(
        port=2200, permit_root_login="forced-commands-only",
        password_authentication=False, pubkey_authentication=True,
        x11_forwarding=True, permit_empty_passwords=False)
    assert config.parse_settings(config.apply_settings("", settings)) == settings


def test_apply_does_not_duplicate_on_reapply():
    once = config.apply_settings("", SshdSettings(port=22))
    twice = config.apply_settings(once, SshdSettings(port=2222))
    assert twice.count("Port ") == 1
    assert config.parse_settings(twice).port == 2222


# --- argv + reader ----------------------------------------------------------

def test_sshd_test_argv():
    assert commands.sshd_test_argv("/tmp/cand") == ["sshd", "-t", "-f", "/tmp/cand"]


def test_current_settings_reads_file(tmp_path):
    p = tmp_path / "sshd_config"
    p.write_text("Port 2022\nPermitRootLogin no\n")
    s = reader.current_settings(str(p))
    assert s.port == 2022 and s.permit_root_login == "no"
    # a missing file yields defaults
    assert reader.current_settings(str(tmp_path / "missing")) == DEFAULTS
