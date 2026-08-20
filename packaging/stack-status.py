#!/usr/bin/env python3
"""stack-status — drift detector for the GeST / HeDE / GeSI release stack.

Prints a version-truth matrix across every place a version lives and fails
(exit 1) if the sources disagree. It is the executable form of the pre-release
rituals ("is everything in sync before I tag?", "did the ISO actually install
the version I bumped, or fall back to a stale binpkg?").

Sources it reconciles:

  gest   source        pyproject.toml + gest/__init__.py  (must agree)
         overlay       newest packaging/overlay/app-admin/gest/gest-*.ebuild
                       + its Manifest DIST digest
  hede   source        hede/CMakeLists.txt  project(hede VERSION ...)
  ---- optional, path-provided ----------------------------------------------
  gest   Amphitheater  newest <amphi>/app-admin/gest/gest-*.ebuild   (--amphitheater)
  hede   Amphitheater  newest <amphi>/gui-apps/hede/hede-*.ebuild
  gest   last ISO      the version catalyst actually merged            (--build-log)
  hede   last ISO      + whether a *binary package* was reused (the silent-
                       binpkg-fallback bug that stranded hede at 0.3.0)

Usage:
    packaging/stack-status.py [--amphitheater DIR] [--build-log FILE]
                              [--strict] [--json]

Exit: 0 = coherent (warnings allowed), 1 = drift/error (or any warning under
--strict). Pure stdlib, so it runs in the dependency-light CI subset.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GEST_OVERLAY = REPO / "packaging" / "overlay" / "app-admin" / "gest"

_SEMVER = r"(\d+\.\d+\.\d+)"
_EBUILD_RE = re.compile(rf"^gest-{_SEMVER}\.ebuild$")
_HEDE_EBUILD_RE = re.compile(rf"^hede-{_SEMVER}\.ebuild$")
_GEST_EBUILD_RE = re.compile(rf"^gest-{_SEMVER}\.ebuild$")
_DIST_RE = re.compile(
    rf"^DIST gest-{_SEMVER}\.tar\.gz \d+ "
    r"BLAKE2B [0-9a-f]{128} SHA512 [0-9a-f]{128}$")
_ASSIGN_RE = lambda name: re.compile(  # noqa: E731 — small local helper
    rf'^\s*{name}\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)
_CMAKE_HEDE_RE = re.compile(rf"project\(hede\s+VERSION\s+{_SEMVER}")
# emerge/catalyst build-log line:  >>> Emerging [binary ](N of M) cat/pkg-ver::repo
_EMERGE_RE = re.compile(
    rf"^>>> Emerging (?P<bin>binary )?\(\d+ of \d+\) "
    rf"(?P<pkg>app-admin/gest|gui-apps/hede)-{_SEMVER}")


def _semver_key(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def _first_group(pattern: re.Pattern[str], text: str) -> str | None:
    m = pattern.search(text)
    return m.group(1) if m else None


def _newest(versions: set[str]) -> str | None:
    return max(versions, key=_semver_key) if versions else None


def _ebuild_versions(dir_: Path, rx: re.Pattern[str]) -> set[str]:
    if not dir_.is_dir():
        return set()
    return {m.group(1) for p in dir_.glob("*.ebuild")
            if (m := rx.match(p.name))}


class Report:
    def __init__(self) -> None:
        self.checks: list[tuple[str, str, str]] = []  # (level, title, detail)

    def add(self, level: str, title: str, detail: str = "") -> None:
        self.checks.append((level, title, detail))

    ok = lambda self, t, d="": self.add("OK", t, d)      # noqa: E731
    warn = lambda self, t, d="": self.add("WARN", t, d)  # noqa: E731
    fail = lambda self, t, d="": self.add("FAIL", t, d)  # noqa: E731

    def worst(self) -> str:
        levels = {lvl for lvl, _, _ in self.checks}
        for lvl in ("FAIL", "WARN", "OK"):
            if lvl in levels:
                return lvl
        return "OK"


def gather(amphi: Path | None, build_log: Path | None) -> tuple[dict, Report]:
    r = Report()
    facts: dict[str, dict[str, str | None]] = {"gest": {}, "hede": {}}

    # --- gest source (pyproject + __init__ must agree) -----------------------
    pyproj = _first_group(_ASSIGN_RE("version"),
                          (REPO / "pyproject.toml").read_text(encoding="utf-8"))
    dunder = _first_group(_ASSIGN_RE("__version__"),
                          (REPO / "gest" / "__init__.py").read_text(encoding="utf-8"))
    if pyproj and dunder and pyproj == dunder:
        r.ok("gest source self-consistent", f"pyproject == __init__ == {pyproj}")
    else:
        r.fail("gest source version mismatch",
               f"pyproject.toml={pyproj} vs gest/__init__.py={dunder}")
    gest_src = pyproj or dunder
    facts["gest"]["source"] = gest_src

    # --- gest overlay (newest ebuild + Manifest DIST) ------------------------
    ebuilds = _ebuild_versions(GEST_OVERLAY, _EBUILD_RE)
    manifest = {m.group(1) for line in
                (GEST_OVERLAY / "Manifest").read_text(encoding="utf-8").splitlines()
                if (m := _DIST_RE.match(line.strip()))}
    overlay_latest = _newest(ebuilds)
    facts["gest"]["overlay"] = overlay_latest

    missing_dist = sorted(ebuilds - manifest, key=_semver_key)
    if missing_dist:
        r.fail("overlay ebuilds without a Manifest DIST",
               "emerge would fail 'Insufficient data for checksum': "
               + ", ".join(missing_dist))
    else:
        r.ok("overlay Manifest complete", f"{len(ebuilds)} ebuilds all have DIST digests")

    if gest_src and overlay_latest:
        if gest_src == overlay_latest:
            r.ok("gest source == overlay", gest_src)
        elif _semver_key(gest_src) > _semver_key(overlay_latest):
            r.warn("gest source ahead of overlay (unreleased)",
                   f"source {gest_src} has no gest-{gest_src}.ebuild yet "
                   f"(newest overlay = {overlay_latest}); release-overlay.py writes it on tag")
        else:
            r.fail("overlay ahead of source (backwards)",
                   f"overlay {overlay_latest} > source {gest_src}")

    # --- hede source ---------------------------------------------------------
    hede_src = _first_group(_CMAKE_HEDE_RE,
                            (REPO / "hede" / "CMakeLists.txt").read_text(encoding="utf-8"))
    facts["hede"]["source"] = hede_src
    if hede_src:
        r.ok("hede source version", hede_src)
    else:
        r.fail("hede source version unreadable", "no project(hede VERSION ...) in CMakeLists.txt")
    if not (REPO / "hede" / "packaging" / "hede-9999.ebuild").exists():
        r.fail("hede-9999.ebuild missing", "the version-independent live ebuild is gone")

    # --- Amphitheater overlay (optional) -------------------------------------
    if amphi is not None:
        if not amphi.is_dir():
            r.fail("Amphitheater path not found", str(amphi))
        else:
            a_gest = _newest(_ebuild_versions(amphi / "app-admin" / "gest", _GEST_EBUILD_RE))
            a_hede = _newest(_ebuild_versions(amphi / "gui-apps" / "hede", _HEDE_EBUILD_RE))
            facts["gest"]["amphitheater"] = a_gest
            facts["hede"]["amphitheater"] = a_hede
            _compare(r, "gest", "Amphitheater", gest_src, a_gest)
            _compare(r, "hede", "Amphitheater", hede_src, a_hede)

    # --- last ISO / build log (optional) -------------------------------------
    if build_log is not None:
        if not build_log.is_file():
            r.fail("build log not found", str(build_log))
        else:
            merged: dict[str, tuple[str, bool]] = {}  # pkg -> (version, from_binpkg)
            for line in build_log.read_text(encoding="utf-8", errors="replace").splitlines():
                m = _EMERGE_RE.match(line)
                if m:
                    merged[m.group("pkg")] = (m.group(3), bool(m.group("bin")))
            g = merged.get("app-admin/gest")
            h = merged.get("gui-apps/hede")
            facts["gest"]["iso"] = g[0] if g else None
            facts["hede"]["iso"] = h[0] if h else None
            _iso_check(r, "gest", gest_src, g)
            _iso_check(r, "hede", hede_src, h)
            if g is None and h is None:
                r.warn("no gest/hede emerge lines in build log",
                       "wrong log, or the build reused everything from binpkgs silently")

    return facts, r


def _compare(r: Report, comp: str, where: str, ref: str | None, got: str | None) -> None:
    if got is None:
        r.warn(f"{comp} not found in {where}", "expected a versioned ebuild there")
    elif ref is not None and ref == got:
        r.ok(f"{comp} source == {where}", got)
    else:
        r.fail(f"{comp} {where} drift", f"source {ref} != {where} {got}")


def _iso_check(r: Report, comp: str, ref: str | None, got: tuple[str, bool] | None) -> None:
    if got is None:
        r.warn(f"{comp} not merged in the ISO build", "no emerge line for it in the log")
        return
    ver, from_bin = got
    if from_bin:
        r.fail(f"{comp} ISO used a BINARY package",
               f"merged gest/hede-{ver} from a binpkg — the silent-fallback bug; "
               "image-mutating packages must build from source")
    elif ref is not None and ref != ver:
        r.fail(f"{comp} ISO version drift", f"source {ref} but the ISO merged {ver}")
    else:
        r.ok(f"{comp} ISO merged from source", ver)


_GLYPH = {"OK": "✓", "WARN": "!", "FAIL": "✗"}


def render_table(facts: dict) -> str:
    cols = ["source", "overlay", "amphitheater", "iso"]
    present = [c for c in cols
               if any(facts[comp].get(c) is not None for comp in facts)]
    if not present:
        present = ["source"]
    head = ["component", *present]
    rows = [[comp, *[(facts[comp].get(c) or "—") for c in present]] for comp in facts]
    widths = [max(len(head[i]), *(len(r[i]) for r in rows)) for i in range(len(head))]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    out = [fmt.format(*head), fmt.format(*("-" * w for w in widths))]
    out += [fmt.format(*row) for row in rows]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Drift detector for the GeST/HeDE/GeSI stack.")
    ap.add_argument("--amphitheater", metavar="DIR", type=Path,
                    help="path to a local Amphitheater overlay checkout "
                         "(cross-check gui-apps/hede + app-admin/gest)")
    ap.add_argument("--build-log", metavar="FILE", type=Path,
                    help="a catalyst/emerge build log to check what the last ISO actually merged")
    ap.add_argument("--strict", action="store_true",
                    help="treat warnings as failures (exit 1) — for release/CI gates")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    facts, r = gather(args.amphitheater, args.build_log)

    if args.json:
        print(json.dumps({
            "facts": facts,
            "checks": [{"level": lvl, "title": t, "detail": d} for lvl, t, d in r.checks],
            "worst": r.worst(),
        }, indent=2))
    else:
        print("GeST / HeDE / GeSI stack version status")
        print("=" * 40)
        print(render_table(facts))
        print()
        for lvl, title, detail in r.checks:
            line = f"  {_GLYPH[lvl]} [{lvl:<4}] {title}"
            print(f"{line}\n{'':>11}{detail}" if detail else line)
        print()
        worst = r.worst()
        verdict = {"OK": "coherent", "WARN": "coherent (with warnings)",
                   "FAIL": "DRIFT DETECTED"}[worst]
        print(f"==> {verdict}")

    worst = r.worst()
    if worst == "FAIL" or (worst == "WARN" and args.strict):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
