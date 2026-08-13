"""CI-safe tests for the privilege (sudo/doas) core: rendering, the doas block
upsert/strip preserving other rules, render→parse round-trips, group validation
and argv builders."""

from gest.core.privilege import commands, render
from gest.core.privilege.model import DOAS_BEGIN, EscalationPolicy

# --- group validation -------------------------------------------------------

def test_valid_group():
    assert render.valid_group("wheel") and render.valid_group("_svc") and render.valid_group("op-s")
    for bad in ("", "1bad", "bad name", "UPPER", "a" * 33, "b;rm"):
        assert not render.valid_group(bad)


# --- sudo -------------------------------------------------------------------

def test_render_sudoers_password_and_nopasswd():
    p = render.render_sudoers(EscalationPolicy("sudo", "wheel", passwordless=False))
    assert p == "# Managed by GeST\n%wheel ALL=(ALL:ALL) ALL\n"
    n = render.render_sudoers(EscalationPolicy("sudo", "admin", passwordless=True))
    assert "%admin ALL=(ALL:ALL) NOPASSWD: ALL" in n


def test_parse_sudoers_round_trips_and_ignores_noise():
    for policy in (EscalationPolicy("sudo", "wheel"),
                   EscalationPolicy("sudo", "ops", passwordless=True)):
        assert render.parse_sudoers(render.render_sudoers(policy)) == policy
    assert render.parse_sudoers("# just a comment\nDefaults env_reset\n") is None


# --- doas block -------------------------------------------------------------

def test_render_doas_line_variants():
    assert render.render_doas_line(EscalationPolicy("doas", "wheel")) == "permit persist :wheel"
    assert render.render_doas_line(
        EscalationPolicy("doas", "wheel", passwordless=True)) == "permit nopass :wheel"
    assert render.render_doas_line(
        EscalationPolicy("doas", "wheel", persist=False)) == "permit :wheel"


def test_apply_doas_block_preserves_other_rules_and_round_trips():
    existing = "permit nopass keepme as root\n# a note\n"
    policy = EscalationPolicy("doas", "wheel", passwordless=False, persist=True)
    out = render.apply_doas_block(existing, policy)
    assert "permit nopass keepme as root" in out
    assert "# a note" in out
    assert render.has_doas_block(out)
    assert render.parse_doas_block(out) == policy
    # strip returns exactly the original
    assert render.strip_doas_block(out) == existing


def test_apply_doas_block_is_idempotent():
    once = render.apply_doas_block("", EscalationPolicy("doas", "wheel"))
    twice = render.apply_doas_block(once, EscalationPolicy("doas", "wheel", passwordless=True))
    assert twice.count(DOAS_BEGIN) == 1
    assert render.parse_doas_block(twice).passwordless is True


def test_strip_and_parse_when_absent():
    assert render.strip_doas_block("permit :wheel\n") == "permit :wheel\n"
    assert not render.has_doas_block("permit :wheel\n")
    assert render.parse_doas_block("permit :wheel\n") is None


# --- argv -------------------------------------------------------------------

def test_check_argv_builders():
    assert commands.visudo_check_argv("/tmp/s") == ["visudo", "-c", "-f", "/tmp/s"]
    assert commands.doas_check_argv("/tmp/d") == ["doas", "-C", "/tmp/d"]
