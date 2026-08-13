"""CI-safe tests for the Wi-Fi core: validation, wpa_supplicant.conf block
parse/remove/append, open-network render, wpa_passphrase-output sanitising, header
insertion, and the iw scan/dev parsers."""

from gest.core.wifi import commands, config, reader
from gest.core.wifi.model import WifiNetwork

_CONF = (
    "ctrl_interface=/run/wpa_supplicant\n"
    "update_config=1\n\n"
    'network={\n\tssid="HomeNet"\n\tpsk=deadbeef\n\tkey_mgmt=WPA-PSK\n}\n\n'
    'network={\n\tssid="OpenCafe"\n\tkey_mgmt=NONE\n}\n'
)


# --- validation -------------------------------------------------------------

def test_valid_ssid():
    assert config.valid_ssid("MyNet") and config.valid_ssid("a") and config.valid_ssid("a" * 32)
    for bad in ("", "a" * 33, 'has"quote', "back\\slash", "new\nline"):
        assert not config.valid_ssid(bad)


def test_valid_passphrase():
    assert config.valid_passphrase("12345678") and config.valid_passphrase("x" * 63)
    for bad in ("short", "x" * 64, "with\ttab"):   # too short / too long / tab (<32)
        assert not config.valid_passphrase(bad)


def test_valid_passphrase_rejects_control_chars():
    assert not config.valid_passphrase("has\nnewline")
    assert not config.valid_passphrase("bell\x07here")


# --- parsing ----------------------------------------------------------------

def test_parse_networks_reads_ssid_and_key_mgmt():
    nets = config.parse_networks(_CONF)
    assert nets == [WifiNetwork("HomeNet", "WPA-PSK"), WifiNetwork("OpenCafe", "NONE")]
    assert nets[0].secured and not nets[1].secured


def test_block_ssid():
    assert config.block_ssid('network={\n\tssid="X Y"\n}') == "X Y"
    assert config.block_ssid("network={\n}") is None


# --- editing ----------------------------------------------------------------

def test_remove_network_drops_only_the_match_and_keeps_header():
    out = config.remove_network(_CONF, "HomeNet")
    assert [n.ssid for n in config.parse_networks(out)] == ["OpenCafe"]
    assert "ctrl_interface=" in out


def test_append_and_render_open_network_round_trip():
    base = config.remove_network(_CONF, "OpenCafe")
    out = config.append_network(base, config.render_open_network("OpenCafe"))
    nets = {n.ssid: n for n in config.parse_networks(out)}
    assert set(nets) == {"HomeNet", "OpenCafe"}
    assert not nets["OpenCafe"].secured


def test_ensure_header_added_only_when_missing():
    assert config.ensure_header("network={\n}").startswith("ctrl_interface=")
    already = "ctrl_interface=/x\nnetwork={\n}\n"
    assert config.ensure_header(already) == already


def test_sanitize_block_strips_plaintext_psk():
    out = ('network={\n\tssid="HomeNet"\n\t#psk="mysecret"\n\tpsk=abcd1234\n}\n')
    san = config.sanitize_block(out)
    assert "mysecret" not in san
    assert "#psk" not in san
    assert "psk=abcd1234" in san
    assert config.block_ssid(san) == "HomeNet"


# --- tool-output parsers + argv ---------------------------------------------

def test_parse_iw_dev_and_scan():
    assert reader.parse_iw_dev("phy#0\n\tInterface wlan0\n\tInterface wlan1\n") == \
        ["wlan0", "wlan1"]
    scan = ("BSS aa:bb\n\tSSID: HomeNet\nBSS cc:dd\n\tSSID: \n"
            "BSS ee:ff\n\tSSID: HomeNet\n\tSSID: Cafe\n")
    # unique, first-seen, hidden (empty) skipped
    assert reader.parse_scan_ssids(scan) == ["HomeNet", "Cafe"]


def test_argv_builders_keep_passphrase_out_of_argv():
    assert commands.wpa_passphrase_argv("My Net") == ["wpa_passphrase", "My Net"]
    assert commands.iw_dev_argv() == ["iw", "dev"]
    assert commands.iw_scan_argv("wlan0") == ["iw", "dev", "wlan0", "scan"]
    assert commands.wpa_cli_reconfigure_argv() == ["wpa_cli", "reconfigure"]


def test_configured_networks_reads_file(tmp_path):
    p = tmp_path / "wpa_supplicant.conf"
    p.write_text(_CONF)
    assert [n.ssid for n in reader.configured_networks(str(p))] == ["HomeNet", "OpenCafe"]
    assert reader.configured_networks(str(tmp_path / "missing")) == []
