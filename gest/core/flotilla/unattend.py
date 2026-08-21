"""Compile a Windows **guest-enablement** provisioning payload for a vessel.

Pure string builders — the same discipline as :mod:`.domainxml` (``xml.etree`` +
plain text, no IO). The output is staged onto a small ISO (built by the host edge
with ``xorriso``, see :mod:`.images`) and attached as a third CD-ROM. On first
boot Windows Setup consumes ``autounattend.xml`` (unattended install, virtio
driver injection, a local account, OOBE skip) and, at first logon, runs
``firstboot.ps1`` — which turns the guest into a **RemoteApp-ready** RDP target:

  (a) Remote Desktop enabled          (d) RemoteApp + TSAppAllowList allow-list
  (b) NLA / CredSSP required          (e) qemu-guest-agent + virtio + spice-vdagent
  (c) firewall opened for RDP         (f) the login user (+ Remote Desktop Users)

This is the prerequisite target for the FreeRDP RAIL spike and the 5b engine.
**Host-validated, not CI-able** — a real Windows install must consume the
autounattend, run the firstboot, and launch the RemoteApp. See
``docs/design/flotilla.md`` §5 / §10-phase5 / §12-decision-2.
"""

from __future__ import annotations

from collections.abc import Sequence
from xml.etree import ElementTree as ET

from gest.core.flotilla.model import RemoteAppProgram, Vessel

# The volume label the provisioning ISO is burned with; firstboot finds itself by
# it (drive letters are unpredictable with three CD-ROMs attached).
PROVISION_LABEL = "FLOTILLA"
FIRSTBOOT_PS1 = "firstboot.ps1"
AUTOUNATTEND_XML = "autounattend.xml"

# A throwaway initial password so the local account exists and NLA can be enabled
# at install time. The REAL credential is never baked into the ISO — it lives in
# the Keychain via Gangway `set-password`; this bootstrap value is meant to be
# rotated on first real login. (Never put a real secret here.)
THROWAWAY_PASSWORD = "ChangeMe!Flotilla1"

# The virtio-win layout Setup needs to see the virtio disk/net in the windowsPE
# pass. Drive letters shift with three CD-ROMs, so we list candidate letters by
# the driver folders; PnP ignores paths that don't exist. `w11` also works for
# Windows 10 guests in current virtio-win, but a caller may override the flavor.
_VIRTIO_DRIVE_LETTERS = ("E", "F", "G", "D")
_VIRTIO_DRIVERS = ("viostor", "vioscsi", "NetKVM", "Balloon", "vioserial")

# XML namespaces the unattend schema requires.
_UNS = "urn:schemas-microsoft-com:unattend"
_WCM = "http://schemas.microsoft.com/WMIConfig/2002/State"
_XSI = "http://www.w3.org/2001/XMLSchema-instance"
ET.register_namespace("", _UNS)
ET.register_namespace("wcm", _WCM)
ET.register_namespace("xsi", _XSI)

_ARCH = "amd64"
_TOKEN = "31bf3856ad364e35"  # the Microsoft component publicKeyToken


def _q(tag: str) -> str:
    return f"{{{_UNS}}}{tag}"


def _sub(parent: ET.Element, tag: str, text: str | None = None, **attrs) -> ET.Element:
    el = ET.SubElement(parent, _q(tag), **attrs)
    if text is not None:
        el.text = text
    return el


def _component(settings: ET.Element, name: str) -> ET.Element:
    return _sub(settings, "component", name=name, processorArchitecture=_ARCH,
               publicKeyToken=_TOKEN, language="neutral", versionScope="nonSxS")


def compile_autounattend(vessel: Vessel, programs: Sequence[RemoteAppProgram],
                         username: str, *, win_flavor: str = "w11") -> str:
    """The ``autounattend.xml`` Windows Setup reads off the provisioning CD:
    inject the virtio drivers in windowsPE, create the local ``username`` account,
    skip OOBE, and — at first logon — kick ``firstboot.ps1`` (found by the CD's
    volume label). ``programs`` rides along only so the doc records the intent; the
    allow-list itself is written by :func:`compile_firstboot_ps1`."""
    unattend = ET.Element(_q("unattend"))

    # --- windowsPE: virtio driver injection so Setup sees the disk/NIC ----------
    pe = _sub(unattend, "settings")
    pe.set("pass", "windowsPE")  # `pass` is a keyword — set it after construction
    pnp = _component(pe, "Microsoft-Windows-PnpCustomizationsWinPE")
    paths = _sub(pnp, "DriverPaths")
    key = 1
    for letter in _VIRTIO_DRIVE_LETTERS:
        for drv in _VIRTIO_DRIVERS:
            pac = _sub(paths, "PathAndCredentials")
            pac.set(f"{{{_WCM}}}action", "add")
            pac.set(f"{{{_WCM}}}keyValue", str(key))
            _sub(pac, "Path", f"{letter}:\\{drv}\\{win_flavor}\\{_ARCH}")
            key += 1

    # --- oobeSystem: local account, OOBE skip, firstboot hook -------------------
    oobe_s = _sub(unattend, "settings")
    oobe_s.set("pass", "oobeSystem")
    shell = _component(oobe_s, "Microsoft-Windows-Shell-Setup")

    oobe = _sub(shell, "OOBE")
    for tag in ("HideEULAPage", "HideLocalAccountScreen", "HideOEMRegistrationScreen",
                "HideOnlineAccountScreens", "HideWirelessSetupInOOBE",
                "ProtectYourPC", "SkipMachineOOBE", "SkipUserOOBE"):
        _sub(oobe, tag, "1" if tag != "ProtectYourPC" else "3")

    accounts = _sub(shell, "UserAccounts")
    local = _sub(accounts, "LocalAccounts")
    acct = _sub(local, "LocalAccount")
    acct.set(f"{{{_WCM}}}action", "add")
    pw = _sub(acct, "Password")
    _sub(pw, "Value", THROWAWAY_PASSWORD)
    _sub(pw, "PlainText", "true")
    _sub(acct, "Name", username)
    _sub(acct, "DisplayName", username)
    _sub(acct, "Group", "Administrators")

    # Auto-login once so FirstLogonCommands runs unattended, then firstboot fires.
    auto = _sub(shell, "AutoLogon")
    apw = _sub(auto, "Password")
    _sub(apw, "Value", THROWAWAY_PASSWORD)
    _sub(apw, "PlainText", "true")
    _sub(auto, "Enabled", "true")
    _sub(auto, "LogonCount", "1")
    _sub(auto, "Username", username)

    flc = _sub(shell, "FirstLogonCommands")
    cmd = _sub(flc, "SynchronousCommand")
    cmd.set(f"{{{_WCM}}}action", "add")
    _sub(cmd, "Order", "1")
    _sub(cmd, "Description", "Flotilla guest enablement")
    _sub(cmd, "CommandLine", _firstlogon_command())
    _sub(cmd, "RequiresUserInput", "false")

    ET.indent(unattend)
    body = ET.tostring(unattend, encoding="unicode")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + body + "\n"


def _firstlogon_command() -> str:
    """A one-liner that locates the provisioning CD by its volume label and runs
    ``firstboot.ps1`` off it (drive letter is not known ahead of time)."""
    ps = (
        f"$v = Get-Volume -FileSystemLabel '{PROVISION_LABEL}'; "
        f"$d = $v.DriveLetter; "
        f"Start-Process powershell -Wait -ArgumentList "
        f"'-ExecutionPolicy','Bypass','-NoProfile','-File',"
        f"(\"$($d):\\{FIRSTBOOT_PS1}\")"
    )
    return f'powershell -ExecutionPolicy Bypass -NoProfile -Command "{ps}"'


def compile_firstboot_ps1(vessel: Vessel, programs: Sequence[RemoteAppProgram],
                          username: str) -> str:
    """The first-logon PowerShell that makes the guest a RemoteApp-ready RDP
    target: (a)-(f). With no ``programs`` the allow-list is left permissive (any
    RemoteApp); with programs it is enforced and populated per program."""
    ts = r"HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server"
    rdp_tcp = ts + r"\WinStations\RDP-Tcp"
    allow = r"HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Terminal Server\TSAppAllowList"
    # fDisabledAllowList: 1 = allow list not enforced (any RemoteApp), 0 = enforce
    # the populated list. Empty program set → permissive; else enforce ours.
    disabled = 1 if not programs else 0

    lines: list[str] = [
        "# Flotilla guest enablement — generated; host-validated only.",
        "$ErrorActionPreference = 'Continue'",
        "",
        "# (f) the login user Gangway authenticates as + RDP rights",
        f"$u = '{_ps_lit(username)}'",
        "if (-not (Get-LocalUser -Name $u -ErrorAction SilentlyContinue)) {",
        f"  net user $u '{_ps_lit(THROWAWAY_PASSWORD)}' /add",
        "}",
        "net localgroup 'Remote Desktop Users' $u /add",
        "",
        "# (a) enable Remote Desktop",
        f"Set-ItemProperty -Path '{ts}' -Name 'fDenyTSConnections' -Value 0 -Type DWord",
        "",
        "# (b) require NLA / CredSSP",
        f"Set-ItemProperty -Path '{rdp_tcp}' -Name 'UserAuthentication' -Value 1 -Type DWord",
        f"Set-ItemProperty -Path '{rdp_tcp}' -Name 'SecurityLayer' -Value 2 -Type DWord",
        "",
        "# (c) open the firewall for RDP",
        "Enable-NetFirewallRule -DisplayGroup 'Remote Desktop' -ErrorAction SilentlyContinue",
        'netsh advfirewall firewall set rule group="remote desktop" new enable=Yes',
        "",
        "# (d) RemoteApp allow-list",
        f"New-Item -Path '{allow}' -Force | Out-Null",
        f"Set-ItemProperty -Path '{allow}' -Name 'fDisabledAllowList' "
        f"-Value {disabled} -Type DWord",
        f"Set-ItemProperty -Path '{allow}' -Name 'fHasListOfPrograms' "
        f"-Value {1 if programs else 0} -Type DWord",
    ]

    for p in programs:
        app = allow + "\\Applications\\" + p.key
        vpath = p.vpath or p.path
        lines += [
            "",
            f"#   published RemoteApp: {p.key}",
            f"New-Item -Path '{app}' -Force | Out-Null",
            f"Set-ItemProperty -Path '{app}' -Name 'Name' -Value '{_ps_lit(p.name)}'",
            f"Set-ItemProperty -Path '{app}' -Name 'Path' -Value '{_ps_lit(p.path)}'",
            f"Set-ItemProperty -Path '{app}' -Name 'VPath' -Value '{_ps_lit(vpath)}'",
            f"Set-ItemProperty -Path '{app}' -Name 'CommandLineSetting' "
            f"-Value {int(p.cmdline_setting)} -Type DWord",
        ]

    lines += [
        "",
        "# (e) qemu-guest-agent + virtio + spice-vdagent (from the virtio-win CD)",
        "$tools = Get-ChildItem -Path (Get-Volume | ForEach-Object "
        "{ \"$($_.DriveLetter):\\\" }) -Filter 'virtio-win-guest-tools.exe' "
        "-ErrorAction SilentlyContinue | Select-Object -First 1",
        "if ($tools) { Start-Process -FilePath $tools.FullName "
        "-ArgumentList '/install','/quiet','/norestart' -Wait }",
        "",
        "Restart-Service -Name TermService -Force -ErrorAction SilentlyContinue",
        "",
    ]
    return "\r\n".join(lines)


def _ps_lit(value: str) -> str:
    """Escape a value for a single-quoted PowerShell string literal ('' escapes ')."""
    return value.replace("'", "''")


def staging_files(vessel: Vessel, programs: Sequence[RemoteAppProgram],
                  username: str) -> dict[str, str]:
    """The ``{filename: contents}`` manifest to stage into a directory and burn as
    the provisioning ISO (see :func:`.images.unattend_iso_argv`)."""
    return {
        AUTOUNATTEND_XML: compile_autounattend(vessel, programs, username),
        FIRSTBOOT_PS1: compile_firstboot_ps1(vessel, programs, username),
    }
