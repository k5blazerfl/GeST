"""CI-safe tests for the CPU_FLAGS_X86 / VIDEO_CARDS module (detect + read/write)."""

from gest.core.hwflags import detect, reader, writer

# --------------------------------------------------------------------------- #
# detection (injected runner)
# --------------------------------------------------------------------------- #

def test_detect_cpu_flags_parses_colon_line():
    def runner(argv):
        assert argv == ["cpuid2cpuflags"]
        return 0, "CPU_FLAGS_X86: aes avx mmx sse sse2\n"
    assert detect.detect_cpu_flags(runner) == ["aes", "avx", "mmx", "sse", "sse2"]


def test_detect_cpu_flags_tool_missing_is_empty():
    def runner(argv):
        raise FileNotFoundError
    assert detect.detect_cpu_flags(runner) == []


def test_detect_video_cards_maps_vendors():
    lspci = (
        "00:02.0 VGA compatible controller: Intel Corporation UHD Graphics\n"
        "01:00.0 VGA compatible controller: Advanced Micro Devices [AMD/ATI] Navi\n"
        "02:00.0 Audio device: Some Vendor\n"
    )
    cards = detect.detect_video_cards(lambda argv: (0, lspci))
    assert "intel" in cards and "amdgpu" in cards and "radeonsi" in cards


def test_detect_video_cards_nvidia_and_none():
    nv = "01:00.0 VGA compatible controller: NVIDIA Corporation GA104\n"
    assert detect.detect_video_cards(lambda argv: (0, nv)) == ["nvidia"]
    assert detect.detect_video_cards(lambda argv: (0, "no gpu here\n")) == []


# --------------------------------------------------------------------------- #
# NVIDIA driver branch by GPU architecture codename
# --------------------------------------------------------------------------- #

def _nv(codename):
    return f"01:00.0 VGA compatible controller: NVIDIA Corporation {codename}\n"


def test_nvidia_driver_branch_by_architecture():
    b = detect.nvidia_driver_branch
    assert b(_nv("AD103 [GeForce RTX 4070 Ti]")) == "current"    # Ada
    assert b(_nv("GA104 [GeForce RTX 3070]")) == "current"       # Ampere
    assert b(_nv("TU116 [GeForce GTX 1660]")) == "current"       # Turing
    assert b(_nv("GP104 [GeForce GTX 1080]")) == "current"       # Pascal
    assert b(_nv("GM206 [GeForce GTX 960]")) == "current"        # Maxwell
    assert b(_nv("GK107 [GeForce GT 630]")) == "legacy-470"      # Kepler
    assert b(_nv("GF119 [GeForce GT 610]")) == "legacy-390"      # Fermi
    assert b(_nv("G92 [GeForce 9800 GT]")) == "nouveau"          # Tesla
    assert b(_nv("GT218 [GeForce 210]")) == "nouveau"            # Tesla (GT2xx)


def test_nvidia_driver_branch_none_and_unknown():
    assert detect.nvidia_driver_branch("intel stuff\n") == ""            # no NVIDIA
    # NVIDIA present but no codename spelled out → assume the current driver
    assert detect.nvidia_driver_branch(
        "01:00.0 VGA compatible controller: NVIDIA Corporation [GeForce Something]\n"
    ) == "current"


def test_nvidia_slots_map():
    assert detect.NVIDIA_SLOTS == {"legacy-470": "0/470", "legacy-390": "0/390"}


def test_amd_legacy_radeon_detection():
    assert detect.amd_legacy_radeon(
        "01:00.0 VGA compatible controller: Advanced Micro Devices "
        "[AMD/ATI] Redwood [Radeon HD 5670]") is True          # TeraScale 2
    assert detect.amd_legacy_radeon(
        "01:00.0 VGA compatible controller: Advanced Micro Devices "
        "[AMD/ATI] Navi 22 [Radeon RX 6700 XT]") is False      # modern → amdgpu
    assert detect.amd_legacy_radeon(
        "01:00.0 VGA compatible controller: NVIDIA Corporation GF119") is False


# --------------------------------------------------------------------------- #
# writer → fragment content
# --------------------------------------------------------------------------- #

def test_use_expand_line():
    assert writer.use_expand_line("CPU_FLAGS_X86", ["mmx", "sse"]) == "*/* CPU_FLAGS_X86: mmx sse"
    assert writer.use_expand_line("VIDEO_CARDS", []) == ""


def test_write_cpu_flags_content_and_clear(tmp_path):
    path = str(tmp_path / "50gest-cpuflags")
    cw = writer.write_cpu_flags(["mmx", "sse2"], path=path)
    assert cw.path == path
    assert cw.text == "*/* CPU_FLAGS_X86: mmx sse2\n"
    assert writer.write_cpu_flags([], path=path).text == ""       # empty → delete


def test_write_video_cards_content(tmp_path):
    path = str(tmp_path / "50gest-videocards")
    cw = writer.write_video_cards(["amdgpu", "radeonsi"], path=path)
    assert cw.text == "*/* VIDEO_CARDS: amdgpu radeonsi\n"


# --------------------------------------------------------------------------- #
# reader round-trip
# --------------------------------------------------------------------------- #

def test_reader_round_trips_writer(tmp_path):
    cpu = tmp_path / "50gest-cpuflags"
    cpu.write_text(writer.write_cpu_flags(["aes", "avx"], path=str(cpu)).text)
    assert reader.current_cpu_flags(str(cpu)) == ["aes", "avx"]
    vid = tmp_path / "50gest-videocards"
    vid.write_text(writer.write_video_cards(["intel"], path=str(vid)).text)
    assert reader.current_video_cards(str(vid)) == ["intel"]


def test_reader_missing_file_is_empty(tmp_path):
    assert reader.current_cpu_flags(str(tmp_path / "nope")) == []


def test_detect_cpu_flags_io_error_is_empty():
    def boom(argv):
        raise OSError(5, "Input/output error", "cpuid2cpuflags")
    assert detect.detect_cpu_flags(boom) == []


def test_detect_video_cards_io_error_is_empty():
    def boom(argv):
        raise OSError(5, "Input/output error", "lspci")
    assert detect.detect_video_cards(boom) == []
