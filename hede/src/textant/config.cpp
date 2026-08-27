#include "config.h"

#include <QSettings>
#include <QStandardPaths>

Config Config::load() {
    Config c;
    const QString dir = QStandardPaths::writableLocation(QStandardPaths::ConfigLocation);
    if (dir.isEmpty())
        return c;
    QSettings s(dir + QStringLiteral("/textant/textant.conf"), QSettings::IniFormat);
    c.fontFamily = s.value(QStringLiteral("font/family"), c.fontFamily).toString();
    c.fontSize   = s.value(QStringLiteral("font/size"), c.fontSize).toInt();
    c.scrollback = s.value(QStringLiteral("scrollback/lines"), c.scrollback).toInt();
    return c;
}
