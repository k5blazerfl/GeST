#include "layout.h"

#include "catalog.h"

#include <QSettings>

namespace helm {

static QString appletsKey() { return QStringLiteral("panel/applets"); }

QStringList PanelLayout::parse(const QString &raw) {
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

QStringList PanelLayout::read(const QString &configPath) {
    QSettings s(configPath, QSettings::IniFormat);
    const QString raw = s.value(appletsKey()).toString();
    if (raw.trimmed().isEmpty())
        return defaultApplets();
    return parse(raw);
}

bool PanelLayout::write(const QString &configPath, const QStringList &applets) {
    QSettings s(configPath, QSettings::IniFormat);
    s.setValue(appletsKey(), applets.join(QStringLiteral(", ")));
    s.sync();
    return s.status() == QSettings::NoError;
}

static QString edgeKey() { return QStringLiteral("panel/edge"); }

QStringList PanelLayout::validEdges() {
    return {QStringLiteral("bottom"), QStringLiteral("top")};
}

QString PanelLayout::readEdge(const QString &configPath) {
    QSettings s(configPath, QSettings::IniFormat);
    const QString e = s.value(edgeKey()).toString().trimmed().toLower();
    return validEdges().contains(e) ? e : QStringLiteral("bottom");
}

bool PanelLayout::writeEdge(const QString &configPath, const QString &edge) {
    const QString e = edge.trimmed().toLower();
    QSettings s(configPath, QSettings::IniFormat);
    s.setValue(edgeKey(), validEdges().contains(e) ? e : QStringLiteral("bottom"));
    s.sync();
    return s.status() == QSettings::NoError;
}

} // namespace helm
