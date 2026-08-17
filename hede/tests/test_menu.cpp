#include <QtTest>

#include "power.h"

class TestMenu : public QObject {
    Q_OBJECT
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
};

QTEST_MAIN(TestMenu)
#include "test_menu.moc"
