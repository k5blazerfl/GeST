#include <QtTest>

#include "updatepill.h"

class TestCoreClient : public QObject {
    Q_OBJECT
private slots:
    void pillText() {
        QCOMPARE(helm::updatePillText(0), QString());
        QCOMPARE(helm::updatePillText(-3), QString()); // never negative
        QCOMPARE(helm::updatePillText(1), QStringLiteral("1 update"));
        QCOMPARE(helm::updatePillText(7), QStringLiteral("7 updates"));
    }
    void pillVisibility() {
        QVERIFY(!helm::updatePillVisible(0));
        QVERIFY(!helm::updatePillVisible(-1));
        QVERIFY(helm::updatePillVisible(1));
        QVERIFY(helm::updatePillVisible(42));
    }
};

QTEST_MAIN(TestCoreClient)
#include "test_coreclient.moc"
