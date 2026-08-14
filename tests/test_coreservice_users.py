"""CI-safe tests for the gestd Users adapter — the model->property-bag converters
and the group-membership helper (pure). The variant packing + live passwd/group
reads are exercised by the round-trip on the Gentoo host."""

from gest.core.users.model import Group, User
from gest.coreservice import users_adapter as adapter
from gest.ipc import core_contract


def test_user_to_dict_shape_and_system_flag():
    u = User(name="alice", uid=1000, gid=1000, gecos="Alice", home="/home/alice",
             shell="/bin/zsh")
    d = adapter.user_to_dict(u)
    assert d["name"] == "alice" and d["uid"] == 1000 and d["gid"] == 1000
    assert d["shell"] == "/bin/zsh" and d["full_name"] == "Alice"
    assert d["system"] is False
    assert set(d) == {"name", "uid", "gid", "gecos", "home", "shell", "full_name", "system"}
    assert adapter.user_to_dict(User(name="root", uid=0, gid=0))["system"] is True


def test_group_to_dict_shape():
    d = adapter.group_to_dict(Group("wheel", 10, ["root", "alice"]))
    assert d["name"] == "wheel" and d["gid"] == 10
    assert d["members"] == ["root", "alice"] and d["system"] is True


def test_user_group_names_primary_and_supplementary():
    alice = User(name="alice", uid=1000, gid=1000)
    groups = [
        Group("alice", 1000, []),          # primary (by gid)
        Group("wheel", 10, ["root", "alice"]),
        Group("audio", 18, ["alice"]),
        Group("cdrom", 19, ["bob"]),       # not a member
    ]
    assert adapter.user_group_names(alice, groups) == ["alice", "audio", "wheel"]
    # no primary group found + no memberships → empty
    assert adapter.user_group_names(User("ghost", 999, 999), groups) == []


def test_users_contract_shape():
    assert core_contract.USERS_CORE_IFACE == "org.gentoo.gest.core1.Users"
    assert core_contract.USERS_CORE_PATH == "/org/gentoo/gest/core/Users"
