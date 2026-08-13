"""CI-safe tests for the env.d core: validation, parse/render round-trip
(quoted + unquoted), and the reader over a fixture drop-in."""

from gest.core.envd import commands, config, reader


def test_valid_name_and_value():
    for good in ("EDITOR", "GOPATH", "_X", "PATH2"):
        assert config.valid_name(good)
    for bad in ("", "1BAD", "bad-name", "has space", "x" * 129):
        assert not config.valid_name(bad)
    assert config.valid_value("nvim") and config.valid_value("/home/u/go")
    for bad in ('has"quote', "a\nb", "has # comment", "x" * 513):
        assert not config.valid_value(bad)


def test_valid_vars_requires_nonempty_and_all_valid():
    assert config.valid_vars({"EDITOR": "nvim"})
    assert not config.valid_vars({})
    assert not config.valid_vars({"1BAD": "x"})
    assert not config.valid_vars({"EDITOR": 'a"b'})


def test_parse_handles_quoted_and_unquoted():
    text = ('# a comment\n'
            'EDITOR="nvim"\n'
            'GOPATH=/home/u/go\n'
            'EMPTY=""\n')
    assert config.parse_conf(text) == {
        "EDITOR": "nvim",
        "GOPATH": "/home/u/go",
        "EMPTY": "",
    }


def test_render_quotes_sorted_with_marker_and_round_trips():
    variables = {"GOPATH": "/home/u/go", "EDITOR": "nvim"}
    text = config.render_conf(variables)
    assert text.startswith("# Managed by GeST\n")
    assert 'EDITOR="nvim"' in text and 'GOPATH="/home/u/go"' in text
    assert text.index("EDITOR") < text.index("GOPATH")     # sorted
    assert config.parse_conf(text) == variables


def test_env_update_argv():
    assert commands.env_update_argv() == ["env-update"]


def test_current_vars_reads_dropin(tmp_path):
    p = tmp_path / "99gest"
    p.write_text('# Managed by GeST\nEDITOR="vim"\n')
    assert reader.current_vars(str(p)) == {"EDITOR": "vim"}
    assert reader.current_vars(str(tmp_path / "missing")) == {}
