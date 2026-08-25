#include <QtTest>

#include <QDateTime>

#include "client.h"
#include "format.h"
#include "notification.h"

class TestLantern : public QObject {
    Q_OBJECT
  private slots:
    void titleCombinesAppAndSummary() {
        helm::Notification n;
        n.app = QStringLiteral("Mail");
        n.summary = QStringLiteral("Hi");
        QCOMPARE(helm::entryTitle(n), QStringLiteral("Mail — Hi"));
        n.app.clear();
        QCOMPARE(helm::entryTitle(n), QStringLiteral("Hi")); // summary only
        n.summary.clear();
        n.app = QStringLiteral("Mail");
        QCOMPARE(helm::entryTitle(n), QStringLiteral("Mail")); // app only
        n.app.clear();
        QCOMPARE(helm::entryTitle(n), QStringLiteral("(notification)")); // neither
    }

    void relativeTimeBuckets() {
        const QDateTime now = QDateTime::fromString(QStringLiteral("2026-08-24T12:00:00"),
                                                    Qt::ISODate);
        QCOMPARE(helm::relativeTime(now.addSecs(-30), now), QStringLiteral("just now"));
        QCOMPARE(helm::relativeTime(now.addSecs(-5 * 60), now), QStringLiteral("5m ago"));
        QCOMPARE(helm::relativeTime(now.addSecs(-3 * 3600), now), QStringLiteral("3h ago"));
        QCOMPARE(helm::relativeTime(now.addDays(-2), now), QStringLiteral("2d ago"));
        // a week or older → the ISO date
        QCOMPARE(helm::relativeTime(now.addDays(-10), now),
                 now.addDays(-10).date().toString(Qt::ISODate));
        // invalid timestamp → empty
        QVERIFY(helm::relativeTime(QDateTime(), now).isEmpty());
    }

    void parseHistoryReadsTheDaemonJson() {
        // The exact shape GetHistory returns (verified on the bus in slice 2).
        const QString json = QStringLiteral(
            R"([{"actions":[],"app":"Mail","body":"b","icon":"i","id":1,)"
            R"("received":"2026-08-24T12:00:00","seen":false,"summary":"Hi",)"
            R"("timeoutMs":0,"urgency":1}])");
        const QVector<helm::Notification> h = helm::LanternClient::parseHistory(json);
        QCOMPARE(h.size(), 1);
        QCOMPARE(h[0].id, 1u);
        QCOMPARE(h[0].app, QStringLiteral("Mail"));
        QCOMPARE(h[0].summary, QStringLiteral("Hi"));
        QVERIFY(h[0].received.isValid());
        // garbage → empty, never a crash
        QVERIFY(helm::LanternClient::parseHistory(QStringLiteral("nonsense")).isEmpty());
    }
};

QTEST_MAIN(TestLantern)
#include "test_lantern.moc"
