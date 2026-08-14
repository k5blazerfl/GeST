#!/bin/sh
# smoke-headless.sh — Phase 0 headless integration smoke test.
#
# Boots labwc on the wlroots *headless* backend (no real display), launches
# helm-panel inside it, and asserts the panel actually spoke wlr-layer-shell and
# created a layer surface — observed in the client's WAYLAND_DEBUG protocol log.
# This is the harness every later phase reuses.
#
# Usage: smoke-headless.sh /path/to/helm-panel
# Exit:  0 pass · 1 fail · 77 skip (labwc not installed → CTest SKIP_RETURN_CODE)
set -u

PANEL="${1:?usage: smoke-headless.sh <path-to-helm-panel>}"

if ! command -v labwc >/dev/null 2>&1; then
    echo "SKIP: labwc not found — headless integration test skipped"
    exit 77
fi
if [ ! -x "$PANEL" ]; then
    echo "FAIL: helm-panel not executable: $PANEL"
    exit 1
fi

# Hermetic runtime dir + a virtual output for the panel to anchor to.
RUNTIME="$(mktemp -d)"
chmod 700 "$RUNTIME"
export XDG_RUNTIME_DIR="$RUNTIME"
export WLR_BACKENDS=headless
export WLR_LIBINPUT_NO_DEVICES=1
export WLR_HEADLESS_OUTPUTS=1

LOG="$RUNTIME/panel-wayland.log"
mkdir -p "$RUNTIME/labwc"   # empty config → labwc defaults (no autostart)

# The probe runs *inside* the labwc session, so it inherits WAYLAND_DISPLAY.
# $PANEL and $LOG are expanded now; $! / $PANEL_PID stay literal for the probe.
cat > "$RUNTIME/probe.sh" <<EOF
#!/bin/sh
export QT_QPA_PLATFORM=wayland
WAYLAND_DEBUG=1 "$PANEL" 2>"$LOG" &
PANEL_PID=\$!
sleep 3                       # let it connect, bind, and create the surface
kill "\$PANEL_PID" 2>/dev/null || true
pkill -x labwc 2>/dev/null || true   # end the compositor; timeout is the backstop
EOF
chmod +x "$RUNTIME/probe.sh"

timeout 30 labwc -C "$RUNTIME/labwc" -s "$RUNTIME/probe.sh" >"$RUNTIME/labwc.log" 2>&1 || true

cleanup() { rm -rf "$RUNTIME"; }
trap cleanup EXIT

if grep -q "zwlr_layer_shell_v1" "$LOG" 2>/dev/null &&
   grep -q "zwlr_layer_surface_v1" "$LOG" 2>/dev/null; then
    echo "PASS: helm-panel bound wlr-layer-shell and created a layer surface"
    exit 0
fi

echo "FAIL: no layer-shell surface observed in helm-panel's WAYLAND_DEBUG output"
echo "----- helm-panel wayland log (tail) -----"
tail -n 40 "$LOG" 2>/dev/null || echo "(no panel log produced)"
echo "----- labwc log (tail) -----"
tail -n 20 "$RUNTIME/labwc.log" 2>/dev/null || true
exit 1
