#!/usr/bin/env bash
#
# Offline host-validation for Gangway + Drydock — everything that needs NO Wine
# runtime and NO RDP host. Exercises the recipe toolchain plumbing and the .rdp
# round-trip against a *real install* of GeST, in an isolated throwaway HOME.
#
# The Wine- and RDP-host-requiring steps are the checklist in
# docs/host-validation.md (§2 live, §3c live) — this script covers the rest.
#
# Usage:   scripts/host-validation/validate-offline.sh
# Override the entry points (e.g. to run from a checkout without installing):
#   DRYDOCK='python -m gest.tui.drydock.cli' \
#   GANGWAY='python -m gest.tui.gangway.cli' \
#   scripts/host-validation/validate-offline.sh

set -u
DRYDOCK="${DRYDOCK:-drydock}"
GANGWAY="${GANGWAY:-gangway}"
HERE="$(cd "$(dirname "$0")" && pwd)"
RECIPE="$HERE/notepad.recipe"

WORK="$(mktemp -d)"
export HOME="$WORK"          # isolate: every ~/.config, ~/.local write lands here
trap 'rm -rf "$WORK"' EXIT

pass=0; fail=0
ok()   { echo "PASS  $1"; pass=$((pass+1)); }
bad()  { echo "FAIL  $1"; fail=$((fail+1)); }
# check <desc> <expected-rc> <cmd...>
check() { local desc="$1" want="$2"; shift 2; "$@" >/dev/null 2>&1; local rc=$?
          [ "$rc" = "$want" ] && ok "$desc" || bad "$desc (rc=$rc, wanted $want)"; }
# grepped <desc> <needle> <cmd...>
grepped() { local desc="$1" needle="$2"; shift 2
            if "$@" 2>/dev/null | grep -qF "$needle"; then ok "$desc"
            else bad "$desc (missing: $needle)"; fi; }

echo "== Drydock recipe toolchain =="
grepped "lint accepts the sample recipe"      "no issues"     $DRYDOCK lint "$RECIPE"
printf 'recipe: 1\napp: {name: X, id: x}\nbottle: {runner: wine, arch: win64}\nsteps:\n- {action: bogus, params: {}}\n' > "$WORK/bad.recipe"
check   "lint rejects an unknown action"      1               $DRYDOCK lint "$WORK/bad.recipe"
grepped "plan compiles create_prefix"         "wineboot"      $DRYDOCK plan "$RECIPE"
grepped "install (dry run) plans the steps"   "dry run"       $DRYDOCK install "$RECIPE"
check   "materialize builds the bottle"       0               $DRYDOCK materialize "$RECIPE"
grepped "the bottle is listed"                "notepad-test"  $DRYDOCK list
grepped "export-recipe round-trips the bottle" "notepad"      $DRYDOCK export-recipe notepad-test

echo "== Gangway .rdp round-trip + dry run + discovery =="
check   "add a profile"                        0   $GANGWAY add work --host pc.corp --user bob --quality lan
grepped "export a profile to .rdp"             "full address:s:pc.corp"  $GANGWAY export work
$GANGWAY export work -o "$WORK/work.rdp" >/dev/null 2>&1
check   "import the .rdp back"                  0   $GANGWAY import "$WORK/work.rdp" --name copy
grepped "open --dry-run prints the FreeRDP command"  "sdl-freerdp"  $GANGWAY open work --dry-run
grepped "open-file --dry-run resolves an rdp:// URI" "/v:host:3391" $GANGWAY open-file "rdp://host:3391" --dry-run
check   "discover accepts a single-IP range"   0   $GANGWAY discover 127.0.0.1/32 --timeout 0.1
check   "discover refuses an over-large range" 2   $GANGWAY discover 10.0.0.0/8

echo
echo "== $pass passed, $fail failed =="
[ "$fail" = 0 ]
