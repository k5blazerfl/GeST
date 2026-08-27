#pragma once

#include <QString>

// User config, read from $XDG_CONFIG_HOME/textant/textant.conf (INI). Everything
// has a default, so a missing file is fine. P1 scope: font + scrollback; glass
// opacity and world-tint theming arrive with P2.
struct Config {
    QString fontFamily;        // empty -> the built-in monospace default
    int fontSize = 11;
    int scrollback = 1000;

    static Config load();
};
