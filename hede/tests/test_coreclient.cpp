#include <QtTest>

#include "batterypill.h"
#include "networkpill.h"
#include "updatepill.h"

class TestCoreClient : public QObject {
    Q_OBJECT
private slots:
    void pillText() {
        QCOMPARE(helm::updatePillText(0), QString());
        QCOMPARE(helm::updatePillText(-3), QString());
        QCOMPARE(helm::updatePillText(1), QStringLiteral("1 update"));
        QCOMPARE(helm::updatePillText(7), QStringLiteral("7 updates"));
    }
    void pillVisibility() {
        QVERIFY(!helm::updatePillVisible(0));
        QVERIFY(helm::updatePillVisible(1));
    }
    void embedArgs() {
        QCOMPARE(helm::settingsEmbedArgs(QStringLiteral("software")),
                 (QStringList{QStringLiteral("--embed"), QStringLiteral("software")}));
    }

    void networkIcon() {
        QCOMPARE(helm::networkIconName(false, QStringLiteral("wifi")),
                 QStringLiteral("network-offline"));
        QCOMPARE(helm::networkIconName(true, QStringLiteral("wifi")),
                 QStringLiteral("network-wireless"));
        QCOMPARE(helm::networkIconName(true, QStringLiteral("ethernet")),
                 QStringLiteral("network-wired"));
    }
    void networkTip() {
        QCOMPARE(helm::networkTooltip(false, QString(), QString()), QStringLiteral("Offline"));
        QCOMPARE(helm::networkTooltip(true, QStringLiteral("wifi"), QStringLiteral("wlp2s0")),
                 QStringLiteral("Wi-Fi (wlp2s0)"));
    }

    void battery() {
        QCOMPARE(helm::batteryText(false, 50, false), QString()); // no battery → hidden
        QCOMPARE(helm::batteryText(true, 72, false), QStringLiteral("72%"));
        QCOMPARE(helm::batteryText(true, 95, true), QString::fromUtf8("\xE2\x9A\xA1") +
                                                        QStringLiteral("95%"));
    }
};

QTEST_MAIN(TestCoreClient)
#include "test_coreclient.moc"
