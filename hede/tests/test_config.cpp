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
    void appletsDefaultLineup() {
        // No [panel] applets key → the built-in lineup, in the historical order.
        QTemporaryDir dir;
        const QString path = dir.filePath(QStringLiteral("hede.conf"));
        const helm::Config cfg(path);
        const QStringList expected = {
            QStringLiteral("launcher"),   QStringLiteral("taskbar"),
            QStringLiteral("mpris"),      QStringLiteral("update"),
            QStringLiteral("network"),    QStringLiteral("battery"),
            QStringLiteral("brightness"), QStringLiteral("volume"),
            QStringLiteral("dnd"),        QStringLiteral("tray"),
            QStringLiteral("clock"),
        };
        QCOMPARE(cfg.panelApplets(), expected);
    }
    void appletsCustomOrder() {
        // A custom, reordered/subset list is honoured verbatim (order preserved).
        QTemporaryDir dir;
        const QString path = dir.filePath(QStringLiteral("hede.conf"));
        {
            QSettings s(path, QSettings::IniFormat);
            s.setValue(QStringLiteral("panel/applets"),
                       QStringLiteral("launcher, taskbar, clock, tray"));
        }
        const helm::Config cfg(path);
        const QStringList expected = {QStringLiteral("launcher"), QStringLiteral("taskbar"),
                                      QStringLiteral("clock"), QStringLiteral("tray")};
        QCOMPARE(cfg.panelApplets(), expected);
    }
    void appletsTolerateWhitespaceCaseAndEmpties() {
        // Ragged whitespace, mixed case, and empty tokens are cleaned up.
        QTemporaryDir dir;
        const QString path = dir.filePath(QStringLiteral("hede.conf"));
        {
            QSettings s(path, QSettings::IniFormat);
            s.setValue(QStringLiteral("panel/applets"),
                       QStringLiteral("  Launcher , ,TASKBAR,  Clock ,"));
        }
        const helm::Config cfg(path);
        const QStringList expected = {QStringLiteral("launcher"), QStringLiteral("taskbar"),
                                      QStringLiteral("clock")};
        QCOMPARE(cfg.panelApplets(), expected);
    }
    void appletsEmptyStringFallsBackToDefault() {
        // An explicitly empty value is treated as "unset" → default lineup.
        QTemporaryDir dir;
        const QString path = dir.filePath(QStringLiteral("hede.conf"));
        {
            QSettings s(path, QSettings::IniFormat);
            s.setValue(QStringLiteral("panel/applets"), QStringLiteral("   "));
        }
        const helm::Config cfg(path);
        QCOMPARE(cfg.panelApplets().first(), QStringLiteral("launcher"));
        QCOMPARE(cfg.panelApplets().size(), 11);
    }
};

QTEST_MAIN(TestConfig)
#include "test_config.moc"
