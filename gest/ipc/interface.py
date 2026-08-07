"""The D-Bus + polkit contract shared by the GeST frontend and backend.

Keeping these names in one place means the unprivileged frontend, the root
service, and the installed system data files (D-Bus policy, polkit actions)
can never drift apart.
"""

# Well-known bus name claimed by the root service on the *system* bus.
BUS_NAME = "org.gentoo.gest"

# Object path + interface for the software-management (Portage) module.
SOFTWARE_PATH = "/org/gentoo/gest/Software"
SOFTWARE_IFACE = "org.gentoo.gest.Software"

# Object path + interface for the services (OpenRC/systemd) module.
SERVICES_PATH = "/org/gentoo/gest/Services"
SERVICES_IFACE = "org.gentoo.gest.Services"
SERVICES_POLKIT = "org.gentoo.gest.services.manage"

# polkit action id prefix. Concrete actions append the verb, e.g.
# ``org.gentoo.gest.software.install``.
POLKIT_PREFIX = "org.gentoo.gest.software"


def polkit_action(verb: str) -> str:
    """Return the fully-qualified polkit action id for a software verb."""
    return f"{POLKIT_PREFIX}.{verb}"
