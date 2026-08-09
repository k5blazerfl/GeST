"""CI-safe tests for the new-user defaults and authentication-status parsers."""

from gest.core.users import auth, defaults


def test_read_defaults_merges_useradd_and_login_defs(tmp_path):
    (tmp_path / "useradd").write_text(
        "# defaults\nGROUP=100\nHOME=/home\nSHELL=/bin/bash\n"
        "INACTIVE=-1\nEXPIRE=\nSKEL=/etc/skel\n")
    (tmp_path / "login.defs").write_text(
        "# comment\nUMASK\t\t022\nPASS_MAX_DAYS   99999\n")
    d = defaults.read_defaults(str(tmp_path / "useradd"), str(tmp_path / "login.defs"))
    assert d.group == "100" and d.home == "/home" and d.shell == "/bin/bash"
    assert d.inactive == "-1" and d.skel == "/etc/skel" and d.umask == "022"


def test_read_defaults_missing_files_are_empty():
    d = defaults.read_defaults("/nope/useradd", "/nope/login.defs")
    assert d.group == "" and d.shell == "" and d.umask == ""


def test_auth_providers_detect_sss_and_ldap(tmp_path):
    conf = tmp_path / "nsswitch.conf"
    conf.write_text("passwd: files sss\ngroup:  files ldap\nhosts: files dns\n")
    by = {p.name: p.configured for p in auth.read_providers(str(conf))}
    assert by["SSSD"] and by["LDAP"]
    assert not by["NIS"] and not by["Samba / Winbind"]


def test_auth_compat_is_not_treated_as_nis(tmp_path):
    conf = tmp_path / "nsswitch.conf"
    conf.write_text("passwd: compat\ngroup: compat\n")
    by = {p.name: p.configured for p in auth.read_providers(str(conf))}
    assert not by["NIS"]  # stock "compat" default must not read as NIS configured


def test_auth_lines_and_missing_file():
    assert auth.read_providers("/nope/nsswitch.conf")  # no crash, all False
    assert auth.read_lines("/nope/nsswitch.conf") == {"passwd": "", "group": ""}
