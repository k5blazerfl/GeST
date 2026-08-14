#include "theme.h"

#include <QDir>
#include <QFile>
#include <QSettings>
#include <QStandardPaths>

namespace helm {

QString effectiveGtkTheme(const ThemeSpec &s) {
    if (!s.gtkTheme.isEmpty())
        return s.gtkTheme;
    return s.dark ? QStringLiteral("Adwaita-dark") : QStringLiteral("Adwaita");
}

QString gtkSettingsIni(const ThemeSpec &s) {
    QString out = QStringLiteral("[Settings]\n");
    out += QStringLiteral("gtk-application-prefer-dark-theme=%1\n").arg(s.dark ? 1 : 0);
    out += QStringLiteral("gtk-theme-name=%1\n").arg(effectiveGtkTheme(s));
    if (!s.iconTheme.isEmpty())
        out += QStringLiteral("gtk-icon-theme-name=%1\n").arg(s.iconTheme);
    return out;
}

ThemeSpec parseThemeArgs(const QStringList &args) {
    ThemeSpec s;
    for (const QString &a : args) {
        if (a == QLatin1String("--dark"))
            s.dark = true;
        else if (a == QLatin1String("--light"))
            s.dark = false;
        else if (a.startsWith(QLatin1String("--accent=")))
            s.accent = a.section(QLatin1Char('='), 1);
        else if (a.startsWith(QLatin1String("--gtk-theme=")))
            s.gtkTheme = a.section(QLatin1Char('='), 1);
        else if (a.startsWith(QLatin1String("--icon-theme=")))
            s.iconTheme = a.section(QLatin1Char('='), 1);
    }
    return s;
}

static bool writeText(const QString &path, const QString &text) {
    QDir().mkpath(QFileInfo(path).absolutePath());
    QFile f(path);
    if (!f.open(QIODevice::WriteOnly | QIODevice::Text))
        return false;
    return f.write(text.toUtf8()) >= 0;
}

QStringList applyTheme(const ThemeSpec &s) {
    const QString base = QStandardPaths::writableLocation(QStandardPaths::GenericConfigLocation);
    const QString gtk = gtkSettingsIni(s);
    QStringList written;

    for (const QString &ver : {QStringLiteral("gtk-3.0"), QStringLiteral("gtk-4.0")}) {
        const QString path = base + QLatin1Char('/') + ver + QStringLiteral("/settings.ini");
        if (writeText(path, gtk))
            written << path;
    }

    // HeDE's own palette (read by the shell via Config).
    const QString hede = base + QStringLiteral("/hede/hede.conf");
    QDir().mkpath(QFileInfo(hede).absolutePath());
    QSettings conf(hede, QSettings::IniFormat);
    conf.setValue(QStringLiteral("appearance/dark"), s.dark);
    if (!s.accent.isEmpty())
        conf.setValue(QStringLiteral("appearance/accent"), s.accent);
    conf.sync();
    if (conf.status() == QSettings::NoError)
        written << hede;

    return written;
}

} // namespace helm
