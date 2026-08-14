#include <QtTest>

#include "brightness.h"
#include "dndtoggle.h"
#include "volume.h"

class TestQuickSettings : public QObject {
    Q_OBJECT
private slots:
    void volumeParse() {
        const helm::VolumeState a = helm::parseWpctlVolume(QStringLiteral("Volume: 0.55"));
        QVERIFY(a.available && a.percent == 55 && !a.muted);
        const helm::VolumeState m = helm::parseWpctlVolume(QStringLiteral("Volume: 0.00 [MUTED]"));
        QVERIFY(m.available && m.percent == 0 && m.muted);
        QVERIFY(!helm::parseWpctlVolume(QString()).available);
        QVERIFY(!helm::parseWpctlVolume(QStringLiteral("garbage")).available);
    }
    void volumeRounds() {
        QCOMPARE(helm::parseWpctlVolume(QStringLiteral("Volume: 0.126")).percent, 13);
    }
    void volumeIcons() {
        QCOMPARE(helm::volumeIconName(50, true), QStringLiteral("audio-volume-muted"));
        QCOMPARE(helm::volumeIconName(0, false), QStringLiteral("audio-volume-muted"));
        QCOMPARE(helm::volumeIconName(20, false), QStringLiteral("audio-volume-low"));
        QCOMPARE(helm::volumeIconName(50, false), QStringLiteral("audio-volume-medium"));
        QCOMPARE(helm::volumeIconName(90, false), QStringLiteral("audio-volume-high"));
    }
    void dndIcons() {
        QCOMPARE(helm::dndIconName(true), QStringLiteral("notifications-disabled"));
        QCOMPARE(helm::dndIconName(false), QStringLiteral("notifications"));
    }

    void brightnessParse() {
        QCOMPARE(helm::parseBrightnessPercent(QStringLiteral("amdgpu_bl1,backlight,120,47%,255")), 47);
        QCOMPARE(helm::parseBrightnessPercent(QStringLiteral("dev,backlight,255,100%,255")), 100);
        QCOMPARE(helm::parseBrightnessPercent(QString()), -1);
        QCOMPARE(helm::parseBrightnessPercent(QStringLiteral("too,few")), -1);
    }
};

QTEST_MAIN(TestQuickSettings)
#include "test_quicksettings.moc"
