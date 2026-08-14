#include <QtTest>

#include "notification.h"

class TestNotification : public QObject {
    Q_OBJECT
private slots:
    void idsAreMonotonicAndWrap() {
        QCOMPARE(helm::nextNotificationId(0), 1u);
        QCOMPARE(helm::nextNotificationId(5), 6u);
        QCOMPARE(helm::nextNotificationId(0xffffffffu), 1u); // wrap, never 0
    }

    void timeoutRules() {
        QCOMPARE(helm::resolveTimeout(-1, 5000), 5000); // server default
        QCOMPARE(helm::resolveTimeout(0, 5000), 0);     // persist
        QCOMPARE(helm::resolveTimeout(3000, 5000), 3000);
    }

    void capabilitiesAdvertiseBodyAndActions() {
        const QStringList caps = helm::serverCapabilities();
        QVERIFY(caps.contains(QStringLiteral("body")));
        QVERIFY(caps.contains(QStringLiteral("actions")));
    }

    void storePutReplaceDrop() {
        QVector<helm::Notification> s;
        helm::Notification a;
        a.id = 1;
        a.summary = QStringLiteral("one");
        helm::putNotification(s, a);
        QCOMPARE(s.size(), 1);
        // same id replaces (e.g. a Notify with replaces_id)
        a.summary = QStringLiteral("one-updated");
        helm::putNotification(s, a);
        QCOMPARE(s.size(), 1);
        QCOMPARE(s[0].summary, QStringLiteral("one-updated"));
        helm::dropNotification(s, 1);
        QCOMPARE(s.size(), 0);
        helm::dropNotification(s, 999); // no-op
        QCOMPARE(helm::indexOfId(s, 1), -1);
    }
};

QTEST_MAIN(TestNotification)
#include "test_notification.moc"
