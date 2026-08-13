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
    return s.value(QStringLiteral("panel/height"), 32).toInt();
}

QString Config::terminalCommand() const {
    QSettings s(m_path, QSettings::IniFormat);
    return s.value(QStringLiteral("terminal/command"), QStringLiteral("foot")).toString();
}

} // namespace helm
