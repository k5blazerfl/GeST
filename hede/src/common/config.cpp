#include "config.h"

#include <QSettings>
#include <QStandardPaths>

namespace helm {

static QString defaultConfigFile() {
    const QString base = QStandardPaths::writableLocation(QStandardPaths::GenericConfigLocation);
    return base + QStringLiteral("/hede/hede.conf");
}

Config::Config() : m_path(defaultConfigFile()) {}

Config::Config(const QString &path) : m_path(path) {}

int Config::panelHeight() const {
    QSettings s(m_path, QSettings::IniFormat);
    return s.value(QStringLiteral("panel/height"), 46).toInt(); // tokens.bar.height
}

QString Config::terminalCommand() const {
    QSettings s(m_path, QSettings::IniFormat);
    return s.value(QStringLiteral("terminal/command"), QStringLiteral("textant")).toString();
}

QString Config::string(const QString &key, const QString &def) const {
    QSettings s(m_path, QSettings::IniFormat);
    return s.value(key, def).toString();
}

} // namespace helm
