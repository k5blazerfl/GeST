#include <QtTest>

#include <QSettings>
#include <QTemporaryDir>

#include "theme.h"

class TestTheme : public QObject {
    Q_OBJECT
private slots:
    void gtkThemeDerivation() {
        helm::ThemeSpec d;
        d.dark = true;
        QCOMPARE(helm::effectiveGtkTheme(d), QStringLiteral("Adwaita-dark"));
        helm::ThemeSpec l;
        QCOMPARE(helm::effectiveGtkTheme(l), QStringLiteral("Adwaita"));
        helm::ThemeSpec c;
        c.gtkTheme = QStringLiteral("Breeze");
        QCOMPARE(helm::effectiveGtkTheme(c), QStringLiteral("Breeze"));
    }

    void gtkIniContent() {
        helm::ThemeSpec s;
        s.dark = true;
        s.iconTheme = QStringLiteral("Papirus");
        const QString ini = helm::gtkSettingsIni(s);
        QVERIFY(ini.contains(QStringLiteral("gtk-application-prefer-dark-theme=1")));
        QVERIFY(ini.contains(QStringLiteral("gtk-theme-name=Adwaita-dark")));
        QVERIFY(ini.contains(QStringLiteral("gtk-icon-theme-name=Papirus")));
        // light omits the icon line when unset
        QVERIFY(!helm::gtkSettingsIni(helm::ThemeSpec{}).contains(QStringLiteral("icon-theme-name")));
        QVERIFY(helm::gtkSettingsIni(helm::ThemeSpec{})
                    .contains(QStringLiteral("gtk-application-prefer-dark-theme=0")));
    }

    void argParsing() {
        const helm::ThemeSpec s = helm::parseThemeArgs(
            {QStringLiteral("--dark"), QStringLiteral("--accent=#33d6c8"),
             QStringLiteral("--icon-theme=Papirus")});
        QVERIFY(s.dark);
        QCOMPARE(s.accent, QStringLiteral("#33d6c8"));
        QCOMPARE(s.iconTheme, QStringLiteral("Papirus"));
    }

    void applyWritesFiles() {
        QTemporaryDir dir;
        qputenv("XDG_CONFIG_HOME", dir.path().toUtf8());
        helm::ThemeSpec s;
        s.dark = true;
        s.accent = QStringLiteral("#33d6c8");
        const QStringList written = helm::applyTheme(s);
        QVERIFY(written.size() >= 3); // gtk-3.0, gtk-4.0, hede.conf
        QVERIFY(QFile::exists(dir.filePath(QStringLiteral("gtk-3.0/settings.ini"))));
        QVERIFY(QFile::exists(dir.filePath(QStringLiteral("gtk-4.0/settings.ini"))));
        QSettings conf(dir.filePath(QStringLiteral("hede/hede.conf")), QSettings::IniFormat);
        QCOMPARE(conf.value(QStringLiteral("appearance/accent")).toString(),
                 QStringLiteral("#33d6c8"));
        QVERIFY(conf.value(QStringLiteral("appearance/dark")).toBool());
    }
};

QTEST_MAIN(TestTheme)
#include "test_theme.moc"
