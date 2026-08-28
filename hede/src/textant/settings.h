#pragma once

#include <QString>

// Textant's own user settings, read from $XDG_CONFIG_HOME/textant/textant.conf
// (INI). Everything has a default, so a missing file is fine. Distinct from
// helm::Config (hede.conf) which supplies the world accent for theming.
struct Settings {
    QString fontFamily;        // empty -> the built-in monospace default
    int fontSize = 11;
    int scrollback = 1000;
    double opacity = 1.0;      // 1.0 = opaque; < 1 = glass (translucent surface)

    static Settings load();
};
