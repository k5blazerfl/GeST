"""CI-safe tests for the hardware core (pure parsers over fixture text)."""

from gest.core.hardware import reader

_LSCPU = (
    "Architecture:            x86_64\n"
    "  CPU op-mode(s):        32-bit, 64-bit\n"
    "CPU(s):                  8\n"
    "Model name:              AMD Ryzen 7 PRO\n"
    "Flags:                   fpu vme de pse tsc msr pae mce cx8 apic sep\n"
)

_MEMINFO = (
    "MemTotal:       28349636 kB\n"
    "MemFree:        22435768 kB\n"
    "MemAvailable:   24298504 kB\n"
    "Buffers:          123456 kB\n"
    "SwapTotal:       8388604 kB\n"
    "SwapFree:        8388604 kB\n"
)


def test_parse_lscpu_aligns_and_drops_flags():
    lines = reader.parse_lscpu(_LSCPU)
    joined = "\n".join(lines)
    assert "Model name" in joined and "AMD Ryzen 7 PRO" in joined
    assert not any(line.strip().startswith("Flags:") for line in lines)
    # first column is padded to a fixed width -> a ':' lands past the label
    assert any(":" in line and line.index(":") >= 22 for line in lines)


def test_parse_meminfo_selects_and_humanizes():
    lines = reader.parse_meminfo(_MEMINFO)
    joined = "\n".join(lines)
    assert "Total" in joined and "GiB" in joined  # 28349636 kB -> ~27 GiB
    assert "Buffers" not in joined                 # not in the curated set
    labels = [line.split(":")[0].strip() for line in lines]
    assert labels == ["Total", "Available", "Free", "Swap total", "Swap free"]


def test_parse_meminfo_ignores_garbage_lines():
    assert reader.parse_meminfo("not a meminfo file\nMemTotal: notanumber kB\n") == []


def test_human_kib_units():
    assert reader._human_kib(512) == "512.0 KiB"
    assert reader._human_kib(2048).endswith("MiB")
    assert reader._human_kib(4 * 1024 * 1024).endswith("GiB")


def test_dmi_info_reads_curated_fields(tmp_path):
    (tmp_path / "sys_vendor").write_text("ACME Inc.\n")
    (tmp_path / "product_name").write_text("WidgetBook 9000\n")
    (tmp_path / "board_serial").write_text("SECRET-SERIAL\n")  # not curated
    lines = reader.dmi_info(str(tmp_path))
    joined = "\n".join(lines)
    assert "ACME Inc." in joined and "WidgetBook 9000" in joined
    assert "SECRET-SERIAL" not in joined  # serials are deliberately excluded


def test_dmi_info_skips_missing(tmp_path):
    assert reader.dmi_info(str(tmp_path)) == []  # empty dir -> no lines


def test_inventory_uses_injected_runner(tmp_path):
    (tmp_path / "sys_vendor").write_text("ACME Inc.\n")
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(_MEMINFO)

    calls: list[str] = []

    def fake_runner(argv):
        calls.append(argv[0])
        return {"lscpu": _LSCPU, "lspci": "00:00.0 Host bridge: Thing\n"}.get(argv[0], "")

    sections = reader.inventory(
        fake_runner, dmi_dir=str(tmp_path), meminfo_path=str(meminfo)
    )
    by_key = {s.key: s for s in sections}
    assert by_key["system"].lines  # DMI present -> System section included
    assert by_key["cpu"].lines and by_key["memory"].lines
    assert by_key["pci"].lines == ["00:00.0 Host bridge: Thing"]
    assert by_key["usb"].lines == []  # runner returned "" -> empty, no crash
    assert {"lscpu", "lsblk", "lspci", "lsusb"} <= set(calls)


def test_inventory_omits_system_without_dmi(tmp_path):
    sections = reader.inventory(
        lambda argv: "", dmi_dir=str(tmp_path / "nope"), meminfo_path=str(tmp_path / "nope")
    )
    assert "system" not in {s.key for s in sections}
