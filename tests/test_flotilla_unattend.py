"""CI-safe tests for the Flotilla Windows guest-enablement compiler
(:mod:`gest.core.flotilla.unattend`). Pure string/XML work — no ISO is built, no
Windows is booted. The real proof (Setup consumes the autounattend, firstboot
runs, the RemoteApp launches) is host-validated; see the module docstring."""

from __future__ import annotations

from xml.etree import ElementTree as ET

from gest.core.flotilla import unattend
from gest.core.flotilla.model import OS_WINDOWS, RemoteAppProgram, Vessel

_NS = {"u": "urn:schemas-microsoft-com:unattend",
       "wcm": "http://schemas.microsoft.com/WMIConfig/2002/State"}


def _vessel() -> Vessel:
    return Vessel(id="win11", name="Windows 11", os=OS_WINDOWS)


def _programs() -> list[RemoteAppProgram]:
    return [
        RemoteAppProgram(key="notepad", name="Notepad", path=r"C:\Windows\notepad.exe",
                         vpath=r"%SystemRoot%\notepad.exe"),
        RemoteAppProgram(key="wordpad", name="WordPad",
                         path=r"C:\Program Files\Windows NT\Accessories\wordpad.exe"),
    ]


# ---- autounattend.xml --------------------------------------------------
def test_autounattend_is_well_formed_and_has_both_passes():
    xml = unattend.compile_autounattend(_vessel(), _programs(), "flotilla")
    assert xml.startswith("<?xml")
    root = ET.fromstring(xml)  # parses → well-formed with the unattend namespace
    passes = [s.get("pass") for s in root.findall("u:settings", _NS)]
    assert passes == ["windowsPE", "oobeSystem"]


def test_autounattend_creates_the_named_local_account():
    xml = unattend.compile_autounattend(_vessel(), _programs(), "skipper")
    root = ET.fromstring(xml)
    name = root.findtext(".//u:LocalAccounts/u:LocalAccount/u:Name", namespaces=_NS)
    assert name == "skipper"
    # the account is an admin and auto-logs-in once so FirstLogonCommands can run.
    assert root.findtext(".//u:LocalAccount/u:Group", namespaces=_NS) == "Administrators"
    assert root.findtext(".//u:AutoLogon/u:Username", namespaces=_NS) == "skipper"
    assert root.findtext(".//u:AutoLogon/u:Enabled", namespaces=_NS) == "true"


def test_autounattend_firstlogon_finds_the_cd_by_label_and_runs_firstboot():
    xml = unattend.compile_autounattend(_vessel(), _programs(), "flotilla")
    root = ET.fromstring(xml)
    cmd = root.findtext(".//u:FirstLogonCommands/u:SynchronousCommand/u:CommandLine",
                        namespaces=_NS)
    assert unattend.PROVISION_LABEL in cmd  # locates itself by volume label
    assert unattend.FIRSTBOOT_PS1 in cmd  # and runs firstboot.ps1


def test_autounattend_injects_virtio_drivers_in_windowspe():
    xml = unattend.compile_autounattend(_vessel(), _programs(), "flotilla")
    root = ET.fromstring(xml)
    pe = next(s for s in root.findall("u:settings", _NS) if s.get("pass") == "windowsPE")
    paths = [p.text for p in pe.findall(".//u:DriverPaths/u:PathAndCredentials/u:Path", _NS)]
    assert paths, "expected virtio DriverPaths in the windowsPE pass"
    assert any("viostor" in p for p in paths)  # the virtio disk driver Setup needs
    assert any("NetKVM" in p for p in paths)


def test_autounattend_never_bakes_a_real_password():
    # only the documented throwaway bootstrap secret may appear.
    xml = unattend.compile_autounattend(_vessel(), _programs(), "flotilla")
    assert unattend.THROWAWAY_PASSWORD in xml  # the bootstrap value…
    # …and it is clearly a throwaway, not a plausible real credential handle.
    assert "ChangeMe" in unattend.THROWAWAY_PASSWORD


# ---- firstboot.ps1 -----------------------------------------------------
def test_firstboot_enables_rdp_nla_firewall():
    ps = unattend.compile_firstboot_ps1(_vessel(), _programs(), "flotilla")
    assert "fDenyTSConnections" in ps and "-Value 0" in ps  # (a) RDP on
    assert "UserAuthentication" in ps  # (b) NLA / CredSSP
    assert "Remote Desktop" in ps  # (c) firewall group opened


def test_firstboot_installs_guest_tools():
    ps = unattend.compile_firstboot_ps1(_vessel(), _programs(), "flotilla")
    # (e) qemu-guest-agent + virtio + spice-vdagent all ship in the guest-tools exe.
    assert "virtio-win-guest-tools.exe" in ps


def test_firstboot_creates_user_with_rdp_rights():
    ps = unattend.compile_firstboot_ps1(_vessel(), _programs(), "deckhand")
    assert "$u = 'deckhand'" in ps  # (f) the login user…
    assert "Remote Desktop Users" in ps  # …granted RDP logon rights


def test_firstboot_writes_a_tsappallowlist_block_per_program():
    programs = _programs()
    ps = unattend.compile_firstboot_ps1(_vessel(), programs, "flotilla")
    base = r"TSAppAllowList\Applications"
    for p in programs:
        app = base + "\\" + p.key
        assert app in ps  # (d) one Applications\<key> subkey per program
        # each carries Name / Path / VPath / CommandLineSetting.
        assert f"'{p.name}'" in ps
        assert p.path in ps
        assert (p.vpath or p.path) in ps
    assert "CommandLineSetting" in ps
    # a populated list is enforced (fDisabledAllowList = 0), not permissive.
    assert "fDisabledAllowList' -Value 0" in ps


def test_firstboot_empty_program_list_is_permissive():
    # --provision with no --remote-app → RemoteApp-ready but any app allowed.
    ps = unattend.compile_firstboot_ps1(_vessel(), [], "flotilla")
    assert "fDisabledAllowList' -Value 1" in ps
    assert r"TSAppAllowList\Applications" not in ps  # nothing published


def test_firstboot_escapes_single_quotes_in_names():
    prog = RemoteAppProgram(key="app", name="Bob's Editor", path=r"C:\bob's app\e.exe")
    ps = unattend.compile_firstboot_ps1(_vessel(), [prog], "flotilla")
    assert "Bob''s Editor" in ps  # '' escapes a quote in a PowerShell literal
    assert r"C:\bob''s app\e.exe" in ps


# ---- staging manifest --------------------------------------------------
def test_staging_files_manifest():
    files = unattend.staging_files(_vessel(), _programs(), "flotilla")
    assert set(files) == {unattend.AUTOUNATTEND_XML, unattend.FIRSTBOOT_PS1}
    # the manifest contents are exactly the two compilers' output.
    assert files[unattend.AUTOUNATTEND_XML].startswith("<?xml")
    assert "fDenyTSConnections" in files[unattend.FIRSTBOOT_PS1]
