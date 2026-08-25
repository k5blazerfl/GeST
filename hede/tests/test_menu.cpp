#include <QtTest>

#include <QDir>
#include <QFile>
#include <QSize>
#include <QTemporaryDir>
#include <QWidget>

#include "launchermenu.h"
#include "power.h"

class TestMenu : public QObject {
    Q_OBJECT
  private:
    // Point hede.conf at a temp dir carrying `[launcher] style=<style>` so the
    // LauncherMenu picks it up via Config() (which reads XDG_CONFIG_HOME).
    static void writeStyle(QTemporaryDir &dir, const QString &style) {
        QVERIFY(QDir(dir.path()).mkpath(QStringLiteral("hede")));
        QFile f(dir.path() + QStringLiteral("/hede/hede.conf"));
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Text));
        f.write(QStringLiteral("[launcher]\nstyle=%1\n").arg(style).toUtf8());
        f.close();
        qputenv("XDG_CONFIG_HOME", dir.path().toUtf8());
    }

  private slots:
    void powerMapping() {
        using helm::PowerAction;
        using helm::PowerCommand;

        // logind Manager methods — exact names matter (typos = silent no-op).
        QCOMPARE(helm::powerCommand(PowerAction::Suspend).kind, PowerCommand::Logind);
        QCOMPARE(helm::powerCommand(PowerAction::Suspend).method, QStringLiteral("Suspend"));
        QCOMPARE(helm::powerCommand(PowerAction::Reboot).method, QStringLiteral("Reboot"));
        QCOMPARE(helm::powerCommand(PowerAction::PowerOff).method, QStringLiteral("PowerOff"));

        // Lock / Log out go through a shell command.
        const PowerCommand lock = helm::powerCommand(PowerAction::Lock);
        QCOMPARE(lock.kind, PowerCommand::Shell);
        QCOMPARE(lock.argv.value(0), QStringLiteral("swaylock"));

        const PowerCommand out = helm::powerCommand(PowerAction::LogOut);
        QCOMPARE(out.kind, PowerCommand::Shell);
        QCOMPARE(out.argv.value(0), QStringLiteral("loginctl"));
    }

    // The default style builds the two-pane pullout: it has the right rail and no
    // classic caption strip.
    void win7StyleByDefault() {
        QTemporaryDir dir;
        writeStyle(dir, QStringLiteral("win7_two_pane"));
        helm::LauncherMenu menu;
        QCOMPARE(menu.objectName(), QStringLiteral("HelmPullout"));
        QVERIFY(menu.findChild<QWidget *>(QStringLiteral("HelmMenuRail")) != nullptr);
        QVERIFY(menu.findChild<QWidget *>(QStringLiteral("HelmClassicCaption")) == nullptr);
        QCOMPARE(menu.size(), QSize(560, 480));
    }

    // The classic style builds a single column with the caption strip and no rail.
    void classicStyleBuilds() {
        QTemporaryDir dir;
        writeStyle(dir, QStringLiteral("classic"));
        helm::LauncherMenu menu;
        QCOMPARE(menu.objectName(), QStringLiteral("HelmPullout"));
        QVERIFY(menu.findChild<QWidget *>(QStringLiteral("HelmClassicCaption")) != nullptr);
        QVERIFY(menu.findChild<QWidget *>(QStringLiteral("HelmMenuRail")) == nullptr);
        QCOMPARE(menu.size(), QSize(300, 520));
    }

    // An unimplemented/unknown style falls back to the default two-pane build
    // (classic_two_column lands in a later slice).
    void unknownStyleFallsToWin7() {
        QTemporaryDir dir;
        writeStyle(dir, QStringLiteral("classic_two_column"));
        helm::LauncherMenu menu;
        QVERIFY(menu.findChild<QWidget *>(QStringLiteral("HelmMenuRail")) != nullptr);
        QVERIFY(menu.findChild<QWidget *>(QStringLiteral("HelmClassicCaption")) == nullptr);
    }
};

QTEST_MAIN(TestMenu)
#include "test_menu.moc"
