"""CI-safe tests for the disk core (pure lsblk/fstab parsing + validation)."""

import pytest

from gest.core.disk import commands, fstab, reader
from gest.core.disk.fstab import FstabEntry

_LSBLK = """
{
  "blockdevices": [
    {"name":"nvme0n1","size":"476.9G","type":"disk","fstype":null,"mountpoints":[null],
     "children":[
       {"name":"nvme0n1p1","size":"2G","type":"part","fstype":"vfat","mountpoints":["/efi"]},
       {"name":"nvme0n1p2","size":"41G","type":"part","fstype":"swap","mountpoints":["[SWAP]"]},
       {"name":"nvme0n1p3","size":"433G","type":"part","fstype":"ext4","mountpoints":["/"]}
     ]}
  ]
}
"""

_FSTAB = """\
# /etc/fstab: static file system information.
UUID=aaaa-bbbb   /efi    vfat   defaults,noatime  0 2
UUID=1111-2222   /       ext4   defaults          0 1

/dev/sdb1        /mnt/data  ext4  defaults,nofail  0 0
UUID=3333-4444   none    swap   sw                0 0
"""


def test_parse_lsblk_builds_tree():
    devices = reader.parse_lsblk_json(_LSBLK)
    assert len(devices) == 1
    disk = devices[0]
    assert disk.name == "nvme0n1" and disk.type == "disk"
    assert [c.name for c in disk.children] == ["nvme0n1p1", "nvme0n1p2", "nvme0n1p3"]
    assert disk.children[0].mountpoint == "/efi"  # from the mountpoints list
    assert disk.children[0].fstype == "vfat"


def test_parse_lsblk_handles_garbage():
    assert reader.parse_lsblk_json("not json") == []
    assert reader.parse_lsblk_json("{}") == []


def test_parse_fstab_fields_and_skips_comments():
    entries = fstab.parse_fstab(_FSTAB)
    mps = [e.mountpoint for e in entries]
    assert mps == ["/efi", "/", "/mnt/data", "none"]  # comment + blank skipped
    data = next(e for e in entries if e.mountpoint == "/mnt/data")
    assert data.spec == "/dev/sdb1" and data.fstype == "ext4"
    assert data.options == "defaults,nofail" and data.dump == 0 and data.passno == 0


def test_protected_flag():
    entries = {e.mountpoint: e for e in fstab.parse_fstab(_FSTAB)}
    assert entries["/"].protected and entries["/efi"].protected
    assert entries["none"].protected          # swap entry
    assert not entries["/mnt/data"].protected


def test_is_protected_rules():
    assert fstab.is_protected(FstabEntry("x", "/boot", "ext4", "defaults"))
    assert fstab.is_protected(FstabEntry("x", "/mnt/x", "swap", "sw"))  # swap fs
    assert not fstab.is_protected(FstabEntry("x", "/mnt/x", "ext4", "defaults"))


def test_upsert_replaces_by_mountpoint_and_keeps_others():
    out = fstab.upsert_entry(_FSTAB, FstabEntry("LABEL=data", "/mnt/data", "xfs", "defaults"))
    assert "LABEL=data" in out and "xfs" in out
    assert "/dev/sdb1" not in out            # old /mnt/data line replaced
    assert "# /etc/fstab" in out             # comment preserved
    assert out.count("/mnt/data") == 1


def test_upsert_appends_new_entry():
    out = fstab.upsert_entry(_FSTAB, FstabEntry("UUID=zz", "/mnt/new", "ext4", "defaults"))
    assert "/mnt/new" in out
    assert [e.mountpoint for e in fstab.parse_fstab(out)][-1] == "/mnt/new"


def test_remove_entry_drops_only_target():
    out = fstab.remove_entry(_FSTAB, "/mnt/data")
    mps = [e.mountpoint for e in fstab.parse_fstab(out)]
    assert "/mnt/data" not in mps and "/" in mps


@pytest.mark.parametrize("spec,ok", [
    ("/dev/sda1", True), ("UUID=abcd", True), ("LABEL=root", True),
    ("PARTUUID=xx", True), ("bad spec", False), ("relative", False), ("has#hash", False),
])
def test_valid_spec(spec, ok):
    assert fstab.valid_spec(spec) is ok


@pytest.mark.parametrize("mp,ok", [
    ("/mnt/data", True), ("none", True), ("swap", True),
    ("relative", False), ("/has space", False), ("/has#hash", False),
])
def test_valid_mountpoint(mp, ok):
    assert fstab.valid_mountpoint(mp) is ok


@pytest.mark.parametrize("opts,ok", [
    ("defaults", True), ("rw,noatime,nofail", True), ("uid=1000,gid=1000", True),
    ("subvol=/@home", True), ("bad opt", False), ("a,,b", False), ("has#hash", False),
])
def test_valid_options(opts, ok):
    assert fstab.valid_options(opts) is ok


def test_valid_entry_rejects_bad_passno():
    assert not fstab.valid_entry(FstabEntry("/dev/sda1", "/x", "ext4", "defaults", 0, 9))


def test_mount_argv_builds_and_rejects():
    assert commands.mount_argv("/mnt/data") == ["mount", "/mnt/data"]
    assert commands.umount_argv("/mnt/data", umount="/bin/umount") == ["/bin/umount", "/mnt/data"]
    for bad in ("swap", "none", "relative", "/mnt/ x", "/mnt/x;rm"):
        with pytest.raises(ValueError):
            commands.mount_argv(bad)
