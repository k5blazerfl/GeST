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
};

QTEST_MAIN(TestConfig)
#include "test_config.moc"
