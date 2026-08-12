"""Tests for the Portage news reader."""

import pytest

from gest.core.software import news


def test_list_news_parses_unread_and_read():
    text = (
        "News items:\n"
        "  [1]   N  2018-08-07  Migration required for OpenSSH with LDAP\n"
        "  [2]      2019-05-23  Change of ACCEPT_LICENSE default\n"
    )
    items = news.list_news(lambda argv: text)
    assert len(items) == 2
    assert items[0].number == 1 and items[0].unread and "OpenSSH" in items[0].title
    assert items[1].number == 2 and not items[1].unread


def test_read_news_uses_number():
    seen = {}

    def runner(argv):
        seen["argv"] = argv
        return "the news body\n"

    assert news.read_news(5, runner) == "the news body"
    assert seen["argv"] == ["eselect", "news", "read", "5"]


def test_mark_read_argv_valid_selectors():
    assert news.mark_read_argv("all") == ["eselect", "news", "read", "all"]
    assert news.mark_read_argv("new") == ["eselect", "news", "read", "new"]
    assert news.mark_read_argv("7") == ["eselect", "news", "read", "7"]
    assert news.mark_read_argv(" 7 ") == ["eselect", "news", "read", "7"]
    assert news.mark_read_argv("3", "/usr/bin/eselect")[0] == "/usr/bin/eselect"
    assert news.mark_read_argv("3", read=False) == ["eselect", "news", "unread", "3"]


def test_mark_read_argv_rejects_bad_selectors():
    for bad in ("", "0", "-1", "foo", "3; rm -rf /", "all news", "1.2"):
        with pytest.raises(ValueError):
            news.mark_read_argv(bad)


def test_parse_content_splits_headers_and_body():
    raw = (
        "2018-08-07-openssh-ldap-migration\n"
        "  Title      Migration required for OpenSSH with LDAP\n"
        "  Author     Thomas Deutschmann <whissi@gentoo.org>\n"
        "  Posted     2018-08-07\n"
        "  Revision   1\n"
        "\n"
        "If your sshd authenticates against LDAP, migrate.\n"
        "\n"
        "[1] https://wiki.gentoo.org/wiki/SSH/LDAP_migration\n"
        "\n\n"
    )
    c = news.parse_content(raw)
    assert c.headers[0] == ("Title", "Migration required for OpenSSH with LDAP")
    assert dict(c.headers)["Author"] == "Thomas Deutschmann <whissi@gentoo.org>"
    assert c.body[0].startswith("If your sshd")
    assert c.body[-1].startswith("[1] https://")   # trailing blanks trimmed


def test_parse_content_malformed_is_all_body():
    c = news.parse_content("just text\nmore text")
    assert c.headers == [] and c.body == ["just text", "more text"]
