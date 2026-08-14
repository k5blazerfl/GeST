#include <QtTest>

#include "toplevelmodel.h"

class TestToplevelModel : public QObject {
    Q_OBJECT
private slots:
    void upsertAddsThenUpdates() {
        QVector<helm::Toplevel> list;
        helm::upsert(list, {QStringLiteral("a"), QStringLiteral("One"), QString(), false, false});
        helm::upsert(list, {QStringLiteral("b"), QStringLiteral("Two"), QString(), false, false});
        QCOMPARE(list.size(), 2);
        // same key updates in place (no duplicate)
        helm::upsert(list, {QStringLiteral("a"), QStringLiteral("One*"), QString(), true, false});
        QCOMPARE(list.size(), 2);
        QCOMPARE(list[helm::indexOfKey(list, QStringLiteral("a"))].title, QStringLiteral("One*"));
        QVERIFY(list[helm::indexOfKey(list, QStringLiteral("a"))].activated);
    }

    void removeWorks() {
        QVector<helm::Toplevel> list;
        helm::upsert(list, {QStringLiteral("a"), QStringLiteral("One"), QString(), false, false});
        helm::removeKey(list, QStringLiteral("a"));
        QCOMPARE(list.size(), 0);
        helm::removeKey(list, QStringLiteral("nope")); // no-op, no crash
        QCOMPARE(indexOfKey(list, QStringLiteral("a")), -1);
    }

    void labelPrefersTitleThenAppId() {
        QCOMPARE(helm::displayLabel({QStringLiteral("k"), QStringLiteral("Firefox"),
                                     QStringLiteral("org.mozilla.firefox"), false, false}),
                 QStringLiteral("Firefox"));
        QCOMPARE(helm::displayLabel({QStringLiteral("k"), QString(),
                                     QStringLiteral("org.mozilla.firefox"), false, false}),
                 QStringLiteral("org.mozilla.firefox"));
        QCOMPARE(helm::displayLabel({QStringLiteral("k"), QString(), QString(), false, false}),
                 QStringLiteral("(untitled)"));
    }

    void labelElides() {
        const helm::Toplevel t{QStringLiteral("k"),
                               QStringLiteral("A very long window title indeed"), QString(), false,
                               false};
        const QString s = helm::displayLabel(t, 10);
        QCOMPARE(s.size(), 10);
        QVERIFY(s.endsWith(QChar(0x2026))); // …
    }
};

QTEST_MAIN(TestToplevelModel)
#include "test_toplevelmodel.moc"
