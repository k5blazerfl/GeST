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
