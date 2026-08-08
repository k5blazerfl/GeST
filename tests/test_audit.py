"""CI-safe tests for the audit-log formatter."""

from gest.backend.audit import format_audit


def test_format_audit_with_uid_and_detail():
    assert format_audit("AddUser", 1000, "ok", "alice") == (
        "uid=1000 action=AddUser result=ok detail=alice"
    )


def test_format_audit_unknown_uid_no_detail():
    assert format_audit("SetHostname", None, "denied") == (
        "uid=? action=SetHostname result=denied"
    )
