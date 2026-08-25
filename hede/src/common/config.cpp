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
    return s.value(QStringLiteral("terminal/command"), QStringLiteral("foot")).toString();
}

QStringList Config::panelApplets() const {
    QSettings s(m_path, QSettings::IniFormat);
    const QString raw = s.value(QStringLiteral("panel/applets")).toString();
    if (raw.trimmed().isEmpty()) {
        // The built-in lineup — mirrors the historical hard-coded order in
        // panel.cpp so an un-configured bar is unchanged. `taskbar` is the
        // stretch child; `spacer` is available as an explicit flexible gap.
        return {
            QStringLiteral("launcher"),   QStringLiteral("taskbar"),
            QStringLiteral("mpris"),      QStringLiteral("update"),
            QStringLiteral("network"),    QStringLiteral("battery"),
            QStringLiteral("brightness"), QStringLiteral("volume"),
            QStringLiteral("dnd"),        QStringLiteral("tray"),
            QStringLiteral("clock"),
        };
    }
    QStringList out;
    const QStringList tokens = raw.split(QLatin1Char(','), Qt::SkipEmptyParts);
    out.reserve(tokens.size());
    for (const QString &tok : tokens) {
        const QString name = tok.trimmed().toLower();
        if (!name.isEmpty())
            out.append(name);
    }
    return out;
}

QString Config::string(const QString &key, const QString &def) const {
    QSettings s(m_path, QSettings::IniFormat);
    return s.value(key, def).toString();
}

} // namespace helm
