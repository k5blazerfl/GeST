#!/bin/sh
# Install the GeST privileged backend: the root D-Bus service + polkit actions.
#
#   sudo ./install-backend.sh      # install
#   sudo ./install-backend.sh -u   # uninstall
#
# NOTE: this is a *development* install. The service loads `gest` from this
# working tree, so root executes code from it — keep the tree trusted and not
# world-writable. For a real deployment, package `gest` system-wide instead.
set -eu

DBUS_CONF=/usr/share/dbus-1/system.d/org.gentoo.gest.conf
DBUS_SVC=/usr/share/dbus-1/system-services/org.gentoo.gest.service
POLKIT=/usr/share/polkit-1/actions/org.gentoo.gest.policy
LAUNCHER=/usr/libexec/gest-backend

if [ "$(id -u)" -ne 0 ]; then
    echo "error: must run as root — try: sudo $0 $*" >&2
    exit 1
fi

if [ "${1:-}" = "-u" ] || [ "${1:-}" = "--uninstall" ]; then
    rm -f "$DBUS_CONF" "$DBUS_SVC" "$POLKIT" "$LAUNCHER"
    command -v rc-service >/dev/null 2>&1 && rc-service dbus reload 2>/dev/null || true
    echo "GeST backend uninstalled."
    exit 0
fi

REPO="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$(command -v python3 || echo /usr/bin/python3)"
echo "Installing GeST backend from: $REPO  (python: $PYTHON)"

install -d /usr/libexec
cat > "$LAUNCHER" <<EOF
#!/bin/sh
# GeST backend launcher (dev install — loads gest from the working tree).
export PYTHONPATH="$REPO"
exec "$PYTHON" -m gest.backend.service "\$@"
EOF
chmod 0755 "$LAUNCHER"
echo "  $LAUNCHER"

install -d /usr/share/dbus-1/system.d
install -m 0644 "$REPO/data/org.gentoo.gest.conf" "$DBUS_CONF"
echo "  $DBUS_CONF"

install -d /usr/share/dbus-1/system-services
install -m 0644 "$REPO/data/org.gentoo.gest.service" "$DBUS_SVC"
echo "  $DBUS_SVC"

install -d /usr/share/polkit-1/actions
install -m 0644 "$REPO/data/org.gentoo.gest.policy" "$POLKIT"
echo "  $POLKIT"

if command -v rc-service >/dev/null 2>&1; then
    rc-service dbus reload 2>/dev/null || echo "  (could not reload dbus automatically — reload it yourself)"
fi

echo "Done. The service bus-activates on first call from the GeST TUI."
