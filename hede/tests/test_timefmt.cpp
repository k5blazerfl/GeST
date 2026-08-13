#include <QtTest>

#include "timefmt.h"

class TestTimeFmt : public QObject {
    Q_OBJECT
private slots:
    void ampm() {
        const QDateTime dt(QDate(2026, 8, 13), QTime(15, 7));
        QCOMPARE(helm::formatClock(dt, true), QStringLiteral("3:07 PM"));
    }
    void twentyFour() {
        const QDateTime dt(QDate(2026, 8, 13), QTime(15, 7));
        QCOMPARE(helm::formatClock(dt, false), QStringLiteral("15:07"));
    }
    void midnight() {
        const QDateTime dt(QDate(2026, 8, 13), QTime(0, 0));
        QCOMPARE(helm::formatClock(dt, true), QStringLiteral("12:00 AM"));
    }
};

QTEST_MAIN(TestTimeFmt)
#include "test_timefmt.moc"
