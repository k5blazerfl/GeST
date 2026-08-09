"""CI-safe tests for the licenses core (reader + write builders)."""

from gest.core.licenses import reader, writer

# --------------------------------------------------------------------------- #
# reader
# --------------------------------------------------------------------------- #

def test_read_all_dir_marks_managed_and_parses(tmp_path):
    (tmp_path / "gest").write_text("app-arch/unrar unRAR\n")
    (tmp_path / "vendor").write_text("sys-firmware/intel-microcode intel-ucode\n")
    entries = {e.atom: e for e in reader.read_all(str(tmp_path))}
    assert entries["app-arch/unrar"].managed
    assert entries["app-arch/unrar"].licenses == ["unRAR"]
    assert not entries["sys-firmware/intel-microcode"].managed
    # managed entries sort first
    assert reader.read_all(str(tmp_path))[0].atom == "app-arch/unrar"


def test_read_all_single_file_form_is_external(tmp_path):
    f = tmp_path / "package.license"          # regular file, not a directory
    f.write_text("app-arch/unrar unRAR\n")
    entries = reader.read_all(str(f))
    assert [e.atom for e in entries] == ["app-arch/unrar"]
    assert not entries[0].managed


def test_read_managed_only_gest(tmp_path):
    gest = tmp_path / "gest"
    gest.write_text(
        "# header\n"
        "app-arch/unrar unRAR\n"
        "sys-kernel/linux-firmware @BINARY-REDISTRIBUTABLE\n"
    )
    managed = reader.read_managed(str(gest))
    assert [e.atom for e in managed] == ["app-arch/unrar", "sys-kernel/linux-firmware"]
    assert all(e.managed for e in managed)
    assert managed[1].licenses == ["@BINARY-REDISTRIBUTABLE"]


def test_read_all_missing_is_empty(tmp_path):
    assert reader.read_all(str(tmp_path / "nope")) == []


def test_accept_license_from_make_conf(tmp_path):
    mc = tmp_path / "make.conf"
    mc.write_text('ACCEPT_LICENSE="-* @FREE @BINARY-REDISTRIBUTABLE"\n')
    assert reader.accept_license(str(mc)) == "-* @FREE @BINARY-REDISTRIBUTABLE"
    assert reader.accept_license(str(tmp_path / "none")) == ""


# --------------------------------------------------------------------------- #
# writer
# --------------------------------------------------------------------------- #

def test_build_line():
    assert writer.build_line("app-arch/unrar", ["unRAR"]) == "app-arch/unrar unRAR"
    assert writer.build_line("cat/pkg", ["*"]) == "cat/pkg *"
    assert writer.build_line("cat/pkg", []) == ""            # no licenses → empty


def test_set_licenses_upserts_and_preserves(tmp_path):
    gest = tmp_path / "gest"
    gest.write_text("# note\nsys-firmware/intel-microcode intel-ucode\napp-arch/unrar OLD\n")
    cw = writer.set_licenses("app-arch/unrar", ["unRAR"], path=str(gest))
    assert cw.path == str(gest)
    assert "app-arch/unrar unRAR" in cw.text
    assert "app-arch/unrar OLD" not in cw.text                # replaced
    assert "sys-firmware/intel-microcode intel-ucode" in cw.text   # sibling kept
    assert "# note" in cw.text                                 # comment kept


def test_set_licenses_empty_removes_entry(tmp_path):
    gest = tmp_path / "gest"
    gest.write_text("app-arch/unrar unRAR\nsys-kernel/x @FREE\n")
    cw = writer.set_licenses("app-arch/unrar", [], path=str(gest))
    assert "app-arch/unrar" not in cw.text
    assert "sys-kernel/x @FREE" in cw.text


def test_set_accept_license_edits_make_conf(tmp_path):
    mc = tmp_path / "make.conf"
    mc.write_text('# hdr\nUSE="x"\n')
    cw = writer.set_accept_license("-* @FREE", path=str(mc))
    assert cw.path == str(mc)
    assert 'ACCEPT_LICENSE="-* @FREE"' in cw.text
    assert "# hdr" in cw.text and 'USE="x"' in cw.text          # rest preserved
