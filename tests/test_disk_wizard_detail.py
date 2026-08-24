"""The Disk gate's detail panel — the bottom 40% of the right pane that explains
the focused row. Headless: build the gate over an App with the disks stubbed,
then read the panel text and drive focus to prove it tracks the selection."""

from __future__ import annotations

import urwid

from gest.core.disk import reader as disk_reader
from gest.core.install import assemble
from gest.tui.runtime import App
from gest.tui.screens.install import wizard as wz

_DISK = disk_reader.BlockDevice(
    name="sda", size="238.5G", type="disk", fstype="", mountpoint="",
    children=[
        disk_reader.BlockDevice(name="sda1", size="1G", type="part",
                                fstype="vfat", mountpoint="/boot", children=[]),
        disk_reader.BlockDevice(name="sda2", size="237.5G", type="part",
                                fstype="ext4", mountpoint="/", children=[]),
    ])


def _disk_step(monkeypatch, *, disk="sda"):
    monkeypatch.setattr(disk_reader, "list_block_devices", lambda: [_DISK])
    app = App()
    sel = assemble.propose("desktop")
    sel.disk = disk
    step = wz.DiskStep(app, sel)
    app._stack.append(step)
    return step


def _panel_text(step) -> str:
    return step._detail_text.get_text()[0]


def test_right_pane_is_split_list_over_detail(monkeypatch):
    step = _disk_step(monkeypatch)
    # _compose_body returns (body, cycle_container, [0]); the body's first item is
    # the Columns(rail, right). The right column is a Pile of two weighted boxes.
    body, _cyc, _pos = step._compose_body()
    cols = body.contents[0][0]
    right = cols.contents[1][0]
    assert isinstance(right, urwid.Pile)
    # Pile contents opts are (sizing, amount) tuples; both boxes are weighted.
    weights = [opts[1] for _w, opts in right.contents]
    assert weights == [3, 2]            # 60/40


def test_target_disk_detail_leads_with_instruction_and_lists_partitions(monkeypatch):
    step = _disk_step(monkeypatch)
    # Focus starts on the first actionable row — "Target disk".
    text = _panel_text(step)
    assert text.startswith("Select the target disk you would like to install onto.")
    assert "sda1" in text and "sda2" in text and "ext4" in text
    assert "erased" in text.lower()
    # The erase note carries the red `error` attribute.
    attrs = [a for a, _run in step._detail_text.get_text()[1]]
    assert "error" in attrs


def test_detail_tracks_focus_movement(monkeypatch):
    step = _disk_step(monkeypatch)
    assert "Select the target disk" in _panel_text(step)   # Target disk detail
    step.handle_key("down")                                 # → next actionable row
    moved = _panel_text(step)
    assert "Select the target disk" not in moved            # panel changed with focus
    # The next actionable row (ESP on UEFI) carries its own instruction.
    assert "EFI System Partition" in moved


def test_no_disk_prompts_to_pick(monkeypatch):
    step = _disk_step(monkeypatch, disk="")
    text = _panel_text(step).lower()
    assert "select the target disk you would like to install onto" in text
