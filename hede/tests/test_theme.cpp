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
        QTemporaryDir cfg, data;
        qputenv("XDG_CONFIG_HOME", cfg.path().toUtf8());
        qputenv("XDG_DATA_HOME", data.path().toUtf8());
        helm::ThemeSpec s;
        s.dark = true;
        s.accent = QStringLiteral("#33d6c8");
        const QStringList written = helm::applyTheme(s);
        QVERIFY(written.size() >= 4); // gtk-3.0, gtk-4.0, hede.conf, themerc
        QVERIFY(QFile::exists(cfg.filePath(QStringLiteral("gtk-3.0/settings.ini"))));
        QVERIFY(QFile::exists(cfg.filePath(QStringLiteral("gtk-4.0/settings.ini"))));
        QVERIFY(QFile::exists(data.filePath(QStringLiteral("themes/Helm/labwc/themerc"))));
        QSettings conf(cfg.filePath(QStringLiteral("hede/hede.conf")), QSettings::IniFormat);
        QCOMPARE(conf.value(QStringLiteral("appearance/accent")).toString(),
                 QStringLiteral("#33d6c8"));
        QVERIFY(conf.value(QStringLiteral("appearance/dark")).toBool());
    }

    void themercColours() {
        // Focused titlebar is a top-lit gradient: the accent at the top, a
        // shadowed accent (×0.82) at the bottom. Label uses the palette's
        // luminance rule (teal → black text, navy → white).
        helm::ThemeSpec teal;
        teal.accent = QStringLiteral("#33d6c8");
        const QString t = helm::themercBody(teal);
        QVERIFY(t.contains(QStringLiteral("window.active.title.bg: Gradient Vertical")));
        QVERIFY(t.contains(QStringLiteral("window.active.title.bg.color: #33d6c8")));
        QVERIFY(t.contains(QStringLiteral("window.active.title.bg.colorTo: #2aafa4"))); // ×0.82
        QVERIFY(t.contains(QStringLiteral("window.active.label.text.color: #000000")));

        helm::ThemeSpec navy;
        navy.accent = QStringLiteral("#0a1633");
        QVERIFY(helm::themercBody(navy).contains(
            QStringLiteral("window.active.label.text.color: #ffffff")));

        // Light vs dark pick different neutral surfaces for the unfocused bar.
        QVERIFY(helm::themercBody(helm::ThemeSpec{})
                    .contains(QStringLiteral("window.inactive.title.bg.color: #f6fafb")));
        helm::ThemeSpec dark;
        dark.dark = true;
        QVERIFY(helm::themercBody(dark).contains(
            QStringLiteral("window.inactive.title.bg.color: #0e2c34")));

        // Empty accent falls back to the Harbor default so the bar is always tinted.
        QVERIFY(helm::themercBody(helm::ThemeSpec{})
                    .contains(QStringLiteral("window.active.title.bg.color: #3aa6c4")));
    }

    // --from-world: with no explicit accent, the themerc takes the active
    // world's accent, and it is NOT persisted back to hede.conf (so a later
    // world switch still re-tints).
    void applyFromWorldUsesWorldAccent() {
        QTemporaryDir cfg, data, worlds;
        qputenv("XDG_CONFIG_HOME", cfg.path().toUtf8());
        qputenv("XDG_DATA_HOME", data.path().toUtf8());
        // a world fixture with a distinctive accent
        const QString hdir = QDir(worlds.path()).filePath(QStringLiteral("harbor"));
        QDir().mkpath(hdir);
        {
            QFile y(QDir(hdir).filePath(QStringLiteral("theme.yaml")));
            QVERIFY(y.open(QIODevice::WriteOnly));
            y.write("id: harbor\naccent: '#123456'\n");
        }
        qputenv("HELM_WORLDS_DIR", worlds.path().toLocal8Bit());
        // hede.conf exists but has no explicit appearance/accent
        {
            QSettings c(cfg.filePath(QStringLiteral("hede/hede.conf")), QSettings::IniFormat);
            c.setValue(QStringLiteral("world/id"), QStringLiteral("harbor"));
        }

        helm::applyThemeFromWorld();
        QFile tf(data.filePath(QStringLiteral("themes/Helm/labwc/themerc")));
        QVERIFY(tf.open(QIODevice::ReadOnly));
        QVERIFY(QString::fromUtf8(tf.readAll())
                    .contains(QStringLiteral("window.active.title.bg.color: #123456")));
        // not persisted as an explicit choice
        QSettings c(cfg.filePath(QStringLiteral("hede/hede.conf")), QSettings::IniFormat);
        QVERIFY(c.value(QStringLiteral("appearance/accent")).toString().isEmpty());

        qunsetenv("HELM_WORLDS_DIR");
        qunsetenv("XDG_CONFIG_HOME");
        qunsetenv("XDG_DATA_HOME");
    }

    // An explicit accent wins over the world even via --from-world.
    void applyFromWorldRespectsExplicitAccent() {
        QTemporaryDir cfg, data, worlds;
        qputenv("XDG_CONFIG_HOME", cfg.path().toUtf8());
        qputenv("XDG_DATA_HOME", data.path().toUtf8());
        const QString hdir = QDir(worlds.path()).filePath(QStringLiteral("harbor"));
        QDir().mkpath(hdir);
        {
            QFile y(QDir(hdir).filePath(QStringLiteral("theme.yaml")));
            QVERIFY(y.open(QIODevice::WriteOnly));
            y.write("id: harbor\naccent: '#123456'\n");
        }
        qputenv("HELM_WORLDS_DIR", worlds.path().toLocal8Bit());
        {
            QSettings c(cfg.filePath(QStringLiteral("hede/hede.conf")), QSettings::IniFormat);
            c.setValue(QStringLiteral("appearance/accent"), QStringLiteral("#abcdef"));
        }

        helm::applyThemeFromWorld();
        QFile tf(data.filePath(QStringLiteral("themes/Helm/labwc/themerc")));
        QVERIFY(tf.open(QIODevice::ReadOnly));
        QVERIFY(QString::fromUtf8(tf.readAll())
                    .contains(QStringLiteral("window.active.title.bg.color: #abcdef")));

        qunsetenv("HELM_WORLDS_DIR");
        qunsetenv("XDG_CONFIG_HOME");
        qunsetenv("XDG_DATA_HOME");
    }

    // setWorld writes [world] id, drops the explicit accent, and regenerates the
    // themerc from the new world; an unknown world changes nothing.
    void setWorldSwitchesAndAdoptsAccent() {
        QTemporaryDir cfg, data, worlds;
        qputenv("XDG_CONFIG_HOME", cfg.path().toUtf8());
        qputenv("XDG_DATA_HOME", data.path().toUtf8());
        auto make = [&](const QString &id, const QString &accent) {
            const QString d = QDir(worlds.path()).filePath(id);
            QDir().mkpath(d);
            QFile y(QDir(d).filePath(QStringLiteral("theme.yaml")));
            QVERIFY(y.open(QIODevice::WriteOnly));
            y.write(QStringLiteral("id: %1\naccent: '%2'\n").arg(id, accent).toUtf8());
        };
        make(QStringLiteral("harbor"), QStringLiteral("#3aa6c4"));
        make(QStringLiteral("emberforge"), QStringLiteral("#e8853a"));
        qputenv("HELM_WORLDS_DIR", worlds.path().toLocal8Bit());
        // start with an explicit accent that a world switch should drop
        {
            QSettings c(cfg.filePath(QStringLiteral("hede/hede.conf")), QSettings::IniFormat);
            c.setValue(QStringLiteral("appearance/accent"), QStringLiteral("#ffffff"));
        }

        QVERIFY(!helm::setWorld(QStringLiteral("nope"))); // unknown → false, no change
        QVERIFY(helm::setWorld(QStringLiteral("emberforge")));

        QSettings c(cfg.filePath(QStringLiteral("hede/hede.conf")), QSettings::IniFormat);
        QCOMPARE(c.value(QStringLiteral("world/id")).toString(), QStringLiteral("emberforge"));
        QVERIFY(c.value(QStringLiteral("appearance/accent")).toString().isEmpty()); // dropped
        // themerc regenerated from the new world's accent
        QFile tf(data.filePath(QStringLiteral("themes/Helm/labwc/themerc")));
        QVERIFY(tf.open(QIODevice::ReadOnly));
        QVERIFY(QString::fromUtf8(tf.readAll())
                    .contains(QStringLiteral("window.active.title.bg.color: #e8853a")));

        qunsetenv("HELM_WORLDS_DIR");
        qunsetenv("XDG_CONFIG_HOME");
        qunsetenv("XDG_DATA_HOME");
    }

    // Anti-drift: the committed default asset must equal themercBody(default).
    void themercDefaultMatchesAsset() {
        QFile f(QStringLiteral(HELM_THEMERC_DEFAULT));
        QVERIFY2(f.open(QIODevice::ReadOnly | QIODevice::Text),
                 qPrintable(f.fileName()));
        const QString onDisk = QString::fromUtf8(f.readAll());
        QCOMPARE(onDisk, helm::themercBody(helm::ThemeSpec{}));
    }
};

QTEST_MAIN(TestTheme)
#include "test_theme.moc"
