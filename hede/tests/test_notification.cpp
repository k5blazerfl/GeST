#include <QtTest>

#include <QTemporaryDir>

#include "history.h"
#include "notification.h"
#include "notifyservice.h"

class TestNotification : public QObject {
    Q_OBJECT
  private:
    static helm::Notification make(uint id, const QString &summary) {
        helm::Notification n;
        n.id = id;
        n.summary = summary;
        return n;
    }

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

    void dndSuppressesExceptCritical() {
        // DND off → always show
        QVERIFY(helm::shouldShowToast(false, helm::UrgencyLow));
        QVERIFY(helm::shouldShowToast(false, helm::UrgencyCritical));
        // DND on → suppress, unless critical
        QVERIFY(!helm::shouldShowToast(true, helm::UrgencyLow));
        QVERIFY(!helm::shouldShowToast(true, helm::UrgencyNormal));
        QVERIFY(helm::shouldShowToast(true, helm::UrgencyCritical));
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

    // --- Lantern history (slice 1) ---

    void historyIsNewestFirst() {
        QVector<helm::Notification> h;
        helm::appendHistory(h, make(1, QStringLiteral("first")), 0);
        helm::appendHistory(h, make(2, QStringLiteral("second")), 0);
        QCOMPARE(h.size(), 2);
        QCOMPARE(h[0].id, 2u); // most-recent at the front
        QCOMPARE(h[1].id, 1u);
    }

    void historyDedupesByIdAndMovesToFront() {
        QVector<helm::Notification> h;
        helm::appendHistory(h, make(1, QStringLiteral("one")), 0);
        helm::appendHistory(h, make(2, QStringLiteral("two")), 0);
        // a replaces_id update for id 1: no duplicate, updated text, now newest
        helm::appendHistory(h, make(1, QStringLiteral("one-updated")), 0);
        QCOMPARE(h.size(), 2);
        QCOMPARE(h[0].id, 1u);
        QCOMPARE(h[0].summary, QStringLiteral("one-updated"));
        QCOMPARE(h[1].id, 2u);
    }

    void historyCapDropsOldest() {
        QVector<helm::Notification> h;
        for (uint i = 1; i <= 5; ++i)
            helm::appendHistory(h, make(i, QStringLiteral("n")), 3);
        QCOMPARE(h.size(), 3);
        QCOMPARE(h[0].id, 5u); // newest kept
        QCOMPARE(h[2].id, 3u); // ids 1,2 dropped as oldest
    }

    void jsonRoundTripsAllFields() {
        helm::Notification n;
        n.id = 42;
        n.app = QStringLiteral("Mail");
        n.icon = QStringLiteral("mail-unread");
        n.summary = QStringLiteral("New message");
        n.body = QStringLiteral("Body <b>text</b>");
        n.actions = {QStringLiteral("open"), QStringLiteral("Open")};
        n.timeoutMs = 3000;
        n.urgency = helm::UrgencyCritical;
        n.received = QDateTime::fromString(QStringLiteral("2026-08-24T13:05:00"), Qt::ISODate);
        n.seen = true;

        const helm::Notification r = helm::notificationFromJson(helm::notificationToJson(n));
        QCOMPARE(r.id, n.id);
        QCOMPARE(r.app, n.app);
        QCOMPARE(r.icon, n.icon);
        QCOMPARE(r.summary, n.summary);
        QCOMPARE(r.body, n.body);
        QCOMPARE(r.actions, n.actions);
        QCOMPARE(r.timeoutMs, n.timeoutMs);
        QCOMPARE(r.urgency, n.urgency);
        QCOMPARE(r.received, n.received);
        QCOMPARE(r.seen, n.seen);
    }

    void serializeDeserializePreservesOrder() {
        QVector<helm::Notification> h;
        helm::appendHistory(h, make(1, QStringLiteral("a")), 0);
        helm::appendHistory(h, make(2, QStringLiteral("b")), 0);
        const QVector<helm::Notification> r = helm::deserializeHistory(helm::serializeHistory(h));
        QCOMPARE(r.size(), 2);
        QCOMPARE(r[0].id, 2u);
        QCOMPARE(r[1].summary, QStringLiteral("a"));
        // malformed input yields an empty list, never a crash
        QVERIFY(helm::deserializeHistory(QByteArrayLiteral("not json")).isEmpty());
    }

    void saveLoadRoundTripsAndMissingFileIsEmpty() {
        QTemporaryDir dir;
        const QString path = dir.filePath(QStringLiteral("sub/notifications.json"));
        QVERIFY(helm::loadHistory(path).isEmpty()); // absent → empty, no crash

        QVector<helm::Notification> h;
        helm::appendHistory(h, make(7, QStringLiteral("saved")), 0);
        QVERIFY(helm::saveHistory(path, h)); // also creates the missing subdir
        const QVector<helm::Notification> r = helm::loadHistory(path);
        QCOMPARE(r.size(), 1);
        QCOMPARE(r[0].id, 7u);
        QCOMPARE(r[0].summary, QStringLiteral("saved"));
    }

    // --- Lantern daemon wiring (slice 2), headless via a null toast stack ---

    void serviceRetainsPersistsReloadsAndClears() {
        QTemporaryDir dir;
        const QString path = dir.filePath(QStringLiteral("hede/notifications.json"));
        uint id1 = 0;
        {
            // No ToastStack (headless): the history path is exercised on its own.
            helm::NotifyService svc(nullptr, nullptr, path);
            QVERIFY(svc.history().isEmpty());
            id1 = svc.notify(QStringLiteral("Mail"), 0, QString(), QStringLiteral("Hi"),
                             QStringLiteral("body"), {}, 0);
            const uint id2 = svc.notify(QStringLiteral("Chat"), 0, QString(),
                                        QStringLiteral("Yo"), QStringLiteral("b2"), {}, 0);
            QCOMPARE(svc.history().size(), 2);
            QCOMPARE(svc.history()[0].id, id2);         // newest first
            QVERIFY(svc.history()[0].received.isValid()); // stamped on arrival
        }
        {
            // A fresh daemon reloads the persisted log (survives a restart).
            helm::NotifyService svc(nullptr, nullptr, path);
            QCOMPARE(svc.history().size(), 2);
            QCOMPARE(svc.history()[1].id, id1);
            svc.clearHistory();
            QVERIFY(svc.history().isEmpty());
        }
        {
            // clearHistory() persisted the empty log too.
            helm::NotifyService svc(nullptr, nullptr, path);
            QVERIFY(svc.history().isEmpty());
        }
    }

    void serviceDedupesHistoryOnReplacesId() {
        QTemporaryDir dir;
        const QString path = dir.filePath(QStringLiteral("hede/notifications.json"));
        helm::NotifyService svc(nullptr, nullptr, path);
        const uint id = svc.notify(QStringLiteral("App"), 0, QString(), QStringLiteral("v1"),
                                   QString(), {}, 0);
        svc.notify(QStringLiteral("App"), id, QString(), QStringLiteral("v2"), QString(), {}, 0);
        QCOMPARE(svc.history().size(), 1); // replaces_id updates in place
        QCOMPARE(svc.history()[0].summary, QStringLiteral("v2"));
    }
};

QTEST_MAIN(TestNotification)
#include "test_notification.moc"
