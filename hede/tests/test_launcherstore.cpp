#include <QtTest>

#include "launcherstore.h"

class TestLauncherStore : public QObject {
    Q_OBJECT
  private slots:
    void recordAndRecent() {
        helm::LauncherStore s;
        helm::recordLaunch(s, QStringLiteral("foot"), 100);
        helm::recordLaunch(s, QStringLiteral("foot"), 200);
        helm::recordLaunch(s, QStringLiteral("gest-settings"), 150);
        // foot has 2 launches, gest-settings 1 → foot ranks first (frequency).
        const QStringList recent = helm::recentIds(s, 5);
        QCOMPARE(recent.value(0), QStringLiteral("foot"));
        QCOMPARE(recent.value(1), QStringLiteral("gest-settings"));
    }

    void recentExcludesPinned() {
        helm::LauncherStore s;
        helm::recordLaunch(s, QStringLiteral("foot"), 100);
        helm::recordLaunch(s, QStringLiteral("gest-settings"), 90);
        const QStringList recent = helm::recentIds(s, 5, {QStringLiteral("foot")});
        QVERIFY(!recent.contains(QStringLiteral("foot")));
        QCOMPARE(recent.value(0), QStringLiteral("gest-settings"));
    }

    void recencyTiebreak() {
        helm::LauncherStore s;
        helm::recordLaunch(s, QStringLiteral("a"), 100); // count 1, older
        helm::recordLaunch(s, QStringLiteral("b"), 300); // count 1, newer
        const QStringList recent = helm::recentIds(s, 5);
        QCOMPARE(recent.value(0), QStringLiteral("b")); // newer wins on equal count
    }

    void togglePin() {
        helm::LauncherStore s;
        helm::togglePin(s, QStringLiteral("foot"));
        QVERIFY(s.pinned.contains(QStringLiteral("foot")));
        helm::togglePin(s, QStringLiteral("foot"));
        QVERIFY(!s.pinned.contains(QStringLiteral("foot")));
    }

    void roundTrip() {
        helm::LauncherStore s;
        s.pinned << QStringLiteral("gest-install") << QStringLiteral("foot");
        helm::recordLaunch(s, QStringLiteral("foot"), 1234);
        const helm::LauncherStore r = helm::parseStore(helm::serializeStore(s));
        QCOMPARE(r.pinned, s.pinned);
        QCOMPARE(r.usage.value(QStringLiteral("foot")).count, 1);
        QCOMPARE(r.usage.value(QStringLiteral("foot")).lastUsed, qint64(1234));
    }

    void defaultsFilterToAvailable() {
        const QStringList pins =
            helm::defaultPins({QStringLiteral("foot"), QStringLiteral("gest-settings")});
        QVERIFY(pins.contains(QStringLiteral("foot")));
        QVERIFY(pins.contains(QStringLiteral("gest-settings")));
        QVERIFY(!pins.contains(QStringLiteral("firefox"))); // not available → dropped
    }
};

QTEST_MAIN(TestLauncherStore)
#include "test_launcherstore.moc"
