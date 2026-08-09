"""CI-safe tests for the staged user/group changes model."""

from gest.core.users import pending
from gest.core.users.pending import PendingChanges


def test_stage_add_user_marks_and_counts():
    p = PendingChanges()
    p.stage(pending.add_user_op("dev", "Dev", "/bin/bash", "wheel", False))
    assert len(p) == 1 and not p.is_empty
    assert p.user_marker("dev") == "+"
    assert p.summary() == "+1"
    assert [o.key for o in p.added_users()] == ["dev"]


def test_stage_dedups_same_kind_and_key():
    p = PendingChanges()
    p.stage(pending.mod_user_op("bob", "Bob", "/bin/bash", ""))
    p.stage(pending.mod_user_op("bob", "Bobby", "/bin/zsh", "wheel"))
    assert len(p) == 1
    assert p.user_marker("bob") == "~"


def test_delete_marker_wins_over_edit():
    p = PendingChanges()
    p.stage(pending.mod_user_op("bob", "Bob", "/bin/bash", ""))
    p.stage(pending.set_password_op("bob", "secret"))
    assert p.user_marker("bob") == "~"
    p.stage(pending.del_user_op("bob", True))
    assert p.user_marker("bob") == "-"


def test_set_member_marks_both_user_and_group():
    p = PendingChanges()
    p.stage(pending.set_member_op("wheel", "alice", True))
    assert p.user_marker("alice") == "~"
    assert p.group_marker("wheel") == "~"


def test_remove_for_user_undoes_all_its_ops():
    p = PendingChanges()
    p.stage(pending.add_user_op("dev", "Dev", "/bin/bash", "", False))
    p.stage(pending.set_password_op("dev", "pw"))
    p.stage(pending.set_member_op("wheel", "dev", True))
    p.remove_for_user("dev")
    assert p.user_marker("dev") is None
    # the membership op referenced the group too; it is gone as well
    assert p.group_marker("wheel") is None
    assert p.is_empty


def test_ordered_applies_groups_and_adds_before_deletes():
    p = PendingChanges()
    p.stage(pending.del_user_op("old", False))
    p.stage(pending.add_group_op("team", False))
    p.stage(pending.add_user_op("new", "New", "/bin/bash", "team", False))
    kinds = [o.kind for o in p.ordered()]
    assert kinds.index(pending.ADD_GROUP) < kinds.index(pending.ADD_USER)
    assert kinds.index(pending.ADD_USER) < kinds.index(pending.DEL_USER)


def test_summary_counts_by_category():
    p = PendingChanges()
    p.stage(pending.add_user_op("a", "", "/bin/bash", "", False))
    p.stage(pending.mod_user_op("b", "", "/bin/bash", ""))
    p.stage(pending.del_group_op("c"))
    assert p.summary() == "+1 ~1 -1"
