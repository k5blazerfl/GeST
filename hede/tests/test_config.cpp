#include <QtTest>

#include <QSettings>
#include <QTemporaryDir>

#include "config.h"

class TestConfig : public QObject {
    Q_OBJECT
private slots:
    void defaults() {
        QTemporaryDir dir;
        const QString path = dir.filePath(QStringLiteral("hede.conf"));
        const helm::Config cfg(path);
        QCOMPARE(cfg.panelHeight(), 46); // tokens.bar.height
        QCOMPARE(cfg.terminalCommand(), QStringLiteral("foot"));
    }
    void overrides() {
        QTemporaryDir dir;
        const QString path = dir.filePath(QStringLiteral("hede.conf"));
        {
            QSettings s(path, QSettings::IniFormat);
            s.setValue(QStringLiteral("panel/height"), 40);
            s.setValue(QStringLiteral("terminal/command"), QStringLiteral("alacritty"));
        }
        const helm::Config cfg(path);
        QCOMPARE(cfg.panelHeight(), 40);
        QCOMPARE(cfg.terminalCommand(), QStringLiteral("alacritty"));
    }
    void heightRereadReflectsExternalEdit() {
        // Slice-2 crux (height side): the live-reload watcher fires, then reload()
        // constructs a fresh Config to read the new height and re-reserve the
        // layer-shell zone. This proves a fresh read sees an external rewrite
        // (QSettings does not hand back stale cached data). The applet-list side
        // of the same guarantee lives in test_barnacle. (Ordered applet list now
        // lives in barnacle-lib / helm::PanelLayout, not Config.)
        QTemporaryDir dir;
        const QString path = dir.filePath(QStringLiteral("hede.conf"));
        {
            QSettings s(path, QSettings::IniFormat);
            s.setValue(QStringLiteral("panel/height"), 40);
        }
        QCOMPARE(helm::Config(path).panelHeight(), 40);

        // The editor (or a hand-edit) rewrites the file...
        {
            QSettings s(path, QSettings::IniFormat);
            s.setValue(QStringLiteral("panel/height"), 52);
            s.sync();
        }
        // ...and a fresh Config must reflect it.
        QCOMPARE(helm::Config(path).panelHeight(), 52);
    }
};

QTEST_MAIN(TestConfig)
#include "test_config.moc"
