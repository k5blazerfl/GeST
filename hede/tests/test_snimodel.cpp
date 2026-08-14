#include <QtTest>

#include "snimodel.h"

class TestSniModel : public QObject {
    Q_OBJECT
private slots:
    void host() { QCOMPARE(helm::hostName(1234), QStringLiteral("org.kde.StatusNotifierHost-1234")); }

    void parseBusNameOnly() {
        const helm::SniId id = helm::parseItemService(QStringLiteral(":1.5"), QStringLiteral(":1.5"));
        QCOMPARE(id.service, QStringLiteral(":1.5"));
        QCOMPARE(id.path, QStringLiteral("/StatusNotifierItem"));
    }

    void parsePathOnlyUsesSender() {
        const helm::SniId id = helm::parseItemService(
            QStringLiteral("/org/ayatana/NotificationItem/x"), QStringLiteral(":1.9"));
        QCOMPARE(id.service, QStringLiteral(":1.9"));
        QCOMPARE(id.path, QStringLiteral("/org/ayatana/NotificationItem/x"));
    }

    void parseServiceSlashPath() {
        const helm::SniId id = helm::parseItemService(QStringLiteral(":1.7/StatusNotifierItem"),
                                                      QStringLiteral(":1.7"));
        QCOMPARE(id.service, QStringLiteral(":1.7"));
        QCOMPARE(id.path, QStringLiteral("/StatusNotifierItem"));
        QCOMPARE(id.key(), QStringLiteral(":1.7/StatusNotifierItem"));
    }

    void splitRoundTrips() {
        const helm::SniId id = helm::splitKey(QStringLiteral(":1.3/StatusNotifierItem"));
        QCOMPARE(id.service, QStringLiteral(":1.3"));
        QCOMPARE(id.path, QStringLiteral("/StatusNotifierItem"));
    }

    void registryDedupesAndRemoves() {
        QStringList l;
        QVERIFY(helm::addUnique(l, QStringLiteral("a")));
        QVERIFY(!helm::addUnique(l, QStringLiteral("a"))); // dup rejected
        QCOMPARE(l.size(), 1);
        QVERIFY(helm::removeOne(l, QStringLiteral("a")));
        QVERIFY(!helm::removeOne(l, QStringLiteral("a"))); // already gone
    }
};

QTEST_MAIN(TestSniModel)
#include "test_snimodel.moc"
