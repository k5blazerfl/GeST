#include <QtTest>

#include <QTemporaryDir>

#include "config.h"
#include "wallpaper.h"

class TestWallpaper : public QObject {
    Q_OBJECT
private slots:
    void parseFitModes() {
        QCOMPARE(helm::parseFit(QStringLiteral("fit")), helm::Fit::Fit);
        QCOMPARE(helm::parseFit(QStringLiteral("STRETCH")), helm::Fit::Stretch);
        QCOMPARE(helm::parseFit(QStringLiteral("center")), helm::Fit::Center);
        QCOMPARE(helm::parseFit(QStringLiteral("tile")), helm::Fit::Tile);
        QCOMPARE(helm::parseFit(QStringLiteral("bogus")), helm::Fit::Fill); // default
    }

    void fitContains() { // 100x100 into 200x100 → scaled 100x100, centred
        const QRect r = helm::computeImageTarget({100, 100}, {200, 100}, helm::Fit::Fit);
        QCOMPARE(r, QRect(50, 0, 100, 100));
    }

    void fillCovers() { // 100x100 into 200x100 → scaled 200x200, centred (overflows top/bottom)
        const QRect r = helm::computeImageTarget({100, 100}, {200, 100}, helm::Fit::Fill);
        QCOMPARE(r, QRect(0, -50, 200, 200));
    }

    void stretchAndCenter() {
        QCOMPARE(helm::computeImageTarget({100, 100}, {200, 100}, helm::Fit::Stretch),
                 QRect(0, 0, 200, 100));
        QCOMPARE(helm::computeImageTarget({100, 100}, {200, 100}, helm::Fit::Center),
                 QRect(50, 0, 100, 100));
    }

    void loadDefaultsToColor() {
        QTemporaryDir dir;
        const helm::Config cfg(dir.filePath(QStringLiteral("hede.conf")));
        const helm::Wallpaper w = helm::loadWallpaper(cfg);
        QVERIFY(!w.useImage);
        QCOMPARE(w.color, QColor(QStringLiteral("#0a1633"))); // abyss navy
        QCOMPARE(w.fit, helm::Fit::Fill);
    }

    void loadImageMode() {
        QTemporaryDir dir;
        const QString path = dir.filePath(QStringLiteral("hede.conf"));
        {
            QSettings s(path, QSettings::IniFormat);
            s.setValue(QStringLiteral("wallpaper/mode"), QStringLiteral("image"));
            s.setValue(QStringLiteral("wallpaper/image"), QStringLiteral("/tmp/x.png"));
            s.setValue(QStringLiteral("wallpaper/fit"), QStringLiteral("center"));
        }
        const helm::Wallpaper w = helm::loadWallpaper(helm::Config(path));
        QVERIFY(w.useImage);
        QCOMPARE(w.imagePath, QStringLiteral("/tmp/x.png"));
        QCOMPARE(w.fit, helm::Fit::Center);
    }
};

QTEST_MAIN(TestWallpaper)
#include "test_wallpaper.moc"
