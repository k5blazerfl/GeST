"""Build the ``sdl-freerdp`` command line for a profile.

Pure and **password-free**: the password is fetched from the Keychain at launch
and fed to FreeRDP over stdin (``/from-stdin``), never on argv (which is visible
in ``ps``). The quality profile maps to FreeRDP's network hint + GFX pipeline.
"""

from __future__ import annotations

from gest.core.rdp.model import QUALITY_LAN, QUALITY_WAN, RdpProfile

CLIENT = "sdl-freerdp"

# quality → (network hint, GFX pipeline)
_QUALITY_FLAGS = {
    QUALITY_LAN: ("/network:lan", "/gfx:AVC444"),
    QUALITY_WAN: ("/network:wan", "/gfx:AVC420"),
}
_QUALITY_DEFAULT = ("/network:auto", "/gfx:AVC420")  # balanced


def _onoff(flag: str, enabled: bool) -> str:
    return f"+{flag}" if enabled else f"-{flag}"


def build_argv(profile: RdpProfile, *, share_path: str | None = None,
               from_stdin: bool = True) -> list[str]:
    """The ``sdl-freerdp`` argv for ``profile``. ``share_path`` is the local
    folder shared as a drive when ``drive_redirect`` is set. ``from_stdin`` adds
    ``/from-stdin`` so FreeRDP reads the (missing) password from stdin."""
    argv = [CLIENT, f"/v:{profile.host}:{profile.port}"]
    if profile.username:
        argv.append(f"/u:{profile.username}")
    if profile.domain:
        argv.append(f"/d:{profile.domain}")

    # display
    if profile.fullscreen:
        argv.append("/f")
    else:
        argv.append(f"/size:{profile.width}x{profile.height}")
    if profile.multimon:
        argv.append("/multimon")
    if profile.dynamic_resolution:
        argv.append("/dynamic-resolution")

    # redirection
    argv.append(_onoff("clipboard", profile.clipboard))
    if profile.drive_redirect and share_path:
        argv.append(f"/drive:HeDE,{share_path}")
    argv.append("/sound" if profile.audio_output else "-sound")
    if profile.microphone:
        argv.append("/microphone")
    if profile.printers:
        argv.append("/printer")

    # gateway + security
    if profile.gateway_host:
        argv.append(f"/gateway:g:{profile.gateway_host}")
    argv.append("/sec:nla" if profile.nla else "/sec:rdp")

    # quality
    network, gfx = _QUALITY_FLAGS.get(profile.quality, _QUALITY_DEFAULT)
    argv += [network, gfx]

    # server cert: trust-on-first-use rather than silently ignoring
    argv.append("/cert:tofu")
    if from_stdin:
        argv.append("/from-stdin")
    return argv
