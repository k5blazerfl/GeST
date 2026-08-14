"""Tests for the battery reader (gest.core.hardware.battery.read_battery)."""

from gest.core.hardware.battery import read_battery


def test_reads_first_battery_and_skips_mains(tmp_path):
    root = tmp_path / "power_supply"
    ac = root / "AC0"
    ac.mkdir(parents=True)
    (ac / "type").write_text("Mains\n")
    bat = root / "BAT0"
    bat.mkdir()
    (bat / "type").write_text("Battery\n")
    (bat / "capacity").write_text("72\n")
    (bat / "status").write_text("Discharging\n")

    b = read_battery(str(root))
    assert b.present and b.percent == 72 and b.status == "Discharging" and not b.charging


def test_charging_flag(tmp_path):
    bat = tmp_path / "BAT0"
    bat.mkdir()
    (bat / "type").write_text("Battery\n")
    (bat / "capacity").write_text("95\n")
    (bat / "status").write_text("Charging\n")
    b = read_battery(str(tmp_path))
    assert b.present and b.charging and b.percent == 95


def test_no_battery(tmp_path):
    assert not read_battery(str(tmp_path)).present


def test_missing_root():
    assert not read_battery("/nonexistent/path/xyz").present
