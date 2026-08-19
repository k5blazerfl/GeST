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
        QVERIFY(written.size() >= 6); // gtk-3.0, gtk-4.0, hede.conf, themerc, + 2 boot
        QVERIFY(QFile::exists(cfg.filePath(QStringLiteral("gtk-3.0/settings.ini"))));
        QVERIFY(QFile::exists(cfg.filePath(QStringLiteral("gtk-4.0/settings.ini"))));
        QVERIFY(QFile::exists(data.filePath(QStringLiteral("themes/Helm/labwc/themerc"))));
        // Boot splash is staged under $XDG_DATA_HOME/hede/boot for the installer.
        QVERIFY(QFile::exists(data.filePath(QStringLiteral("hede/boot/plymouth/hede/hede.script"))));
        QVERIFY(QFile::exists(data.filePath(QStringLiteral("hede/boot/grub/hede/theme.txt"))));
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

    // The boot splash tracks the accent: the Plymouth progress bar / fallback
    // fill and the GRUB letterbox / highlighted entry are all accent-derived,
    // and an empty accent falls back to Harbor so the boot is always themed.
    void bootThemeColours() {
        const QString ply = helm::plymouthScriptBody(QStringLiteral("#e8853a")); // ember
        QVERIFY(ply.contains(QStringLiteral("Image.Text(\" \", 0.910, 0.522, 0.227)"))); // bar
        QVERIFY(ply.contains(QStringLiteral("// #e8853a accent")));
        QVERIFY(ply.contains(QStringLiteral("SetBackgroundTopColor(0.145, 0.082, 0.035)"))); // ×0.16

        const QString grub = helm::grubThemeBody(QStringLiteral("#e8853a"));
        QVERIFY(grub.contains(QStringLiteral("desktop-color: \"#251509\"")));        // deep ×0.16
        QVERIFY(grub.contains(QStringLiteral("selected_item_color = \"#f1b689\"")));  // lighten .40

        // Empty accent → Harbor default in both generators.
        QVERIFY(helm::plymouthScriptBody(QString())
                    .contains(QStringLiteral("// #3aa6c4 accent")));
        QVERIFY(helm::grubThemeBody(QString())
                    .contains(QStringLiteral("desktop-color: \"#091b1f\"")));
    }

    // writeBootTheme emits both files under an explicit dir (what the root
    // SyncBootTheme calls via --emit-boot-theme), byte-equal to the generators.
    void writeBootThemeToDir() {
        QTemporaryDir dir;
        const QStringList w = helm::writeBootTheme(dir.path(), QStringLiteral("#e8853a"));
        QCOMPARE(w.size(), 2);
        QFile ply(dir.filePath(QStringLiteral("plymouth/hede/hede.script")));
        QVERIFY(ply.open(QIODevice::ReadOnly));
        QCOMPARE(QString::fromUtf8(ply.readAll()),
                 helm::plymouthScriptBody(QStringLiteral("#e8853a")));
        QFile grub(dir.filePath(QStringLiteral("grub/hede/theme.txt")));
        QVERIFY(grub.open(QIODevice::ReadOnly));
        QCOMPARE(QString::fromUtf8(grub.readAll()),
                 helm::grubThemeBody(QStringLiteral("#e8853a")));
    }

    // activeAccent: explicit [appearance] accent wins, else the active world's.
    void activeAccentPrecedence() {
        QTemporaryDir cfg, worlds;
        qputenv("XDG_CONFIG_HOME", cfg.path().toUtf8());
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
            c.setValue(QStringLiteral("world/id"), QStringLiteral("harbor"));
        }
        QCOMPARE(helm::activeAccent(), QStringLiteral("#123456")); // world accent
        {
            QSettings c(cfg.filePath(QStringLiteral("hede/hede.conf")), QSettings::IniFormat);
            c.setValue(QStringLiteral("appearance/accent"), QStringLiteral("#abcdef"));
        }
        QCOMPARE(helm::activeAccent(), QStringLiteral("#abcdef")); // explicit wins

        qunsetenv("HELM_WORLDS_DIR");
        qunsetenv("XDG_CONFIG_HOME");
    }

    // activeWorldId: hede.conf [world] id, default harbor.
    void activeWorldIdDefaultAndSet() {
        QTemporaryDir cfg;
        qputenv("XDG_CONFIG_HOME", cfg.path().toUtf8());
        QCOMPARE(helm::activeWorldId(), QStringLiteral("harbor")); // default
        {
            QSettings c(cfg.filePath(QStringLiteral("hede/hede.conf")), QSettings::IniFormat);
            c.setValue(QStringLiteral("world/id"), QStringLiteral("stormwatch"));
        }
        QCOMPARE(helm::activeWorldId(), QStringLiteral("stormwatch"));
        qunsetenv("XDG_CONFIG_HOME");
    }

    // emitBootScene copies the world's boot.png over the Plymouth background (so
    // the splash art tracks the biome), overwrites on re-emit, and is a no-op for
    // a world that ships no boot.png (the installed default is left in place).
    void emitBootSceneCopiesWorldBootPng() {
        QTemporaryDir worlds, out;
        auto world = [&](const QString &id, bool withBoot) {
            const QString d = QDir(worlds.path()).filePath(id);
            QDir().mkpath(d);
            QFile y(QDir(d).filePath(QStringLiteral("theme.yaml")));
            QVERIFY(y.open(QIODevice::WriteOnly));
            y.write(QStringLiteral("id: %1\naccent: '#e8853a'\n").arg(id).toUtf8());
            if (withBoot) {
                QFile b(QDir(d).filePath(QStringLiteral("boot.png")));
                QVERIFY(b.open(QIODevice::WriteOnly));
                b.write("PNGDATA");
            }
        };
        world(QStringLiteral("emberforge"), true);
        world(QStringLiteral("bare"), false);
        qputenv("HELM_WORLDS_DIR", worlds.path().toLocal8Bit());

        const QString p = helm::emitBootScene(out.path(), QStringLiteral("emberforge"));
        QCOMPARE(p, out.filePath(QStringLiteral("plymouth/hede/background.png")));
        QFile f(p);
        QVERIFY(f.open(QIODevice::ReadOnly));
        QCOMPARE(f.readAll(), QByteArray("PNGDATA"));
        // re-emit overwrites (QFile::copy would otherwise refuse an existing dst)
        QVERIFY(!helm::emitBootScene(out.path(), QStringLiteral("emberforge")).isEmpty());
        // no boot.png → empty, nothing written
        QVERIFY(helm::emitBootScene(out.path(), QStringLiteral("bare")).isEmpty());

        qunsetenv("HELM_WORLDS_DIR");
    }

    // Anti-drift: the committed boot assets must equal the default generators.
    void bootDefaultsMatchAssets() {
        QFile p(QStringLiteral(HELM_PLYMOUTH_DEFAULT));
        QVERIFY2(p.open(QIODevice::ReadOnly | QIODevice::Text), qPrintable(p.fileName()));
        QCOMPARE(QString::fromUtf8(p.readAll()), helm::plymouthScriptBody(QString()));

        QFile g(QStringLiteral(HELM_GRUB_DEFAULT));
        QVERIFY2(g.open(QIODevice::ReadOnly | QIODevice::Text), qPrintable(g.fileName()));
        QCOMPARE(QString::fromUtf8(g.readAll()), helm::grubThemeBody(QString()));
    }
};

QTEST_MAIN(TestTheme)
#include "test_theme.moc"
