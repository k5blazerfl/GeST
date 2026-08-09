"""CI-safe tests for the binhost core (reader + write builders)."""

from gest.core.binhost import reader, writer
from gest.core.binhost.model import GETBINPKG, REQUIRE_SIGNATURE, Binhost

_GENTOO = (
    "[gentoo]\n"
    "priority = 9959\n"
    "sync-uri = https://d/binpackages/23.0/x86-64/\n"
    "verify-signature = true\n"
    "location = /var/cache/binhost/gentoo\n"
)
_GEST = (
    "[myhost]\nsync-uri = https://h/bin/\nverify-signature = false\n"
)


# --------------------------------------------------------------------------- #
# reader
# --------------------------------------------------------------------------- #

def test_read_all_marks_managed_and_parses(tmp_path):
    (tmp_path / "gentoo.conf").write_text(_GENTOO)
    (tmp_path / "gest.conf").write_text(_GEST)
    hosts = {h.name: h for h in reader.read_all(str(tmp_path))}
    assert hosts["myhost"].managed and not hosts["gentoo"].managed   # gest.conf → managed
    assert hosts["gentoo"].priority == "9959"
    assert hosts["gentoo"].verify_signature is True
    assert hosts["myhost"].verify_signature is False
    # managed hosts sort first
    assert reader.read_all(str(tmp_path))[0].name == "myhost"


def test_read_managed_only_gest_fragment(tmp_path):
    (tmp_path / "gentoo.conf").write_text(_GENTOO)
    (tmp_path / "gest.conf").write_text(_GEST)
    managed = reader.read_managed(str(tmp_path / "gest.conf"))
    assert [h.name for h in managed] == ["myhost"]
    assert all(h.managed for h in managed)


def test_read_all_missing_dir_is_empty(tmp_path):
    assert reader.read_all(str(tmp_path / "nope")) == []


def test_features_state_from_make_conf(tmp_path):
    mc = tmp_path / "make.conf"
    mc.write_text('FEATURES="getbinpkg parallel-fetch"\n')
    st = reader.features_state(str(mc))
    assert st.getbinpkg and not st.require_signature


# --------------------------------------------------------------------------- #
# writer: hosts → gest.conf
# --------------------------------------------------------------------------- #

def test_write_hosts_round_trips_through_reader(tmp_path):
    path = str(tmp_path / "gest.conf")
    hosts = [
        Binhost("a", sync_uri="https://a/", priority="100", verify_signature=True),
        Binhost("b", sync_uri="https://b/", verify_signature=False),
    ]
    cw = writer.write_hosts(hosts, path=path)
    assert cw.path == path
    (tmp_path / "gest.conf").write_text(cw.text)   # emulate the backend applying it
    back = {h.name: h for h in reader.read_managed(path)}
    assert back["a"].priority == "100" and back["a"].verify_signature is True
    assert back["b"].verify_signature is False


def test_write_hosts_empty_deletes_file():
    cw = writer.write_hosts([], path="/etc/portage/binrepos.conf/gest.conf")
    assert cw.text == ""            # empty text → backend unlinks the fragment


def test_upsert_and_remove_host():
    hosts = [Binhost("a", sync_uri="https://a/")]
    hosts = writer.upsert_host(hosts, Binhost("b", sync_uri="https://b/"))
    assert {h.name for h in hosts} == {"a", "b"}
    # upsert with an existing name replaces, not duplicates
    hosts = writer.upsert_host(hosts, Binhost("a", sync_uri="https://a2/"))
    assert len([h for h in hosts if h.name == "a"]) == 1
    assert next(h for h in hosts if h.name == "a").sync_uri == "https://a2/"
    hosts = writer.remove_host(hosts, "a")
    assert {h.name for h in hosts} == {"b"}


# --------------------------------------------------------------------------- #
# writer: FEATURES toggle
# --------------------------------------------------------------------------- #

def test_toggle_token_add_remove_and_preserve():
    assert writer.toggle_token("parallel-fetch", GETBINPKG, True) == "parallel-fetch getbinpkg"
    assert writer.toggle_token("parallel-fetch getbinpkg", GETBINPKG, False) == "parallel-fetch"
    assert writer.toggle_token("getbinpkg", GETBINPKG, True) == "getbinpkg"   # idempotent
    assert writer.toggle_token("", GETBINPKG, False) == ""


def test_set_feature_edits_make_conf_in_place(tmp_path):
    mc = tmp_path / "make.conf"
    mc.write_text('# hdr\nFEATURES="parallel-fetch"\nUSE="x"\n')
    cw = writer.set_feature(REQUIRE_SIGNATURE, True, path=str(mc))
    assert 'FEATURES="parallel-fetch binpkg-request-signature"' in cw.text
    assert "# hdr" in cw.text and 'USE="x"' in cw.text          # rest preserved


def test_set_feature_appends_when_absent(tmp_path):
    mc = tmp_path / "make.conf"
    mc.write_text('USE="x"\n')
    cw = writer.set_feature(GETBINPKG, True, path=str(mc))
    assert 'FEATURES="getbinpkg"' in cw.text
