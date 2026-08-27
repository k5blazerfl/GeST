#include "settings.h"

#include <QSettings>
#include <QStandardPaths>

Settings Settings::load() {
    Settings c;
    const QString dir = QStandardPaths::writableLocation(QStandardPaths::ConfigLocation);
    if (dir.isEmpty())
        return c;
    QSettings s(dir + QStringLiteral("/textant/textant.conf"), QSettings::IniFormat);
    c.fontFamily = s.value(QStringLiteral("font/family"), c.fontFamily).toString();
    c.fontSize   = s.value(QStringLiteral("font/size"), c.fontSize).toInt();
    c.scrollback = s.value(QStringLiteral("scrollback/lines"), c.scrollback).toInt();
    c.opacity    = s.value(QStringLiteral("glass/opacity"), c.opacity).toDouble();
    return c;
}
