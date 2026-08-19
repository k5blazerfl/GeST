#include <QtTest>

#include <QTemporaryDir>

#include "config.h"
#include "wallpaper.h"

class TestWallpaper : public QObject {
    Q_OBJECT
private:
    // Isolate world resolution from the host: unless a test points
    // HELM_WORLDS_DIR at its own fixture, loadWorld() finds nothing.
    QTemporaryDir m_noWorlds;

private slots:
    void init() { qputenv("HELM_WORLDS_DIR", m_noWorlds.path().toLocal8Bit()); }
    void cleanup() { qunsetenv("HELM_WORLDS_DIR"); }

    void parseFitModes() {
        QCOMPARE(helm::parseFit(QStringLiteral("fit")), helm::Fit::Fit);
        QCOMPARE(helm::parseFit(QStringLiteral("contain")), helm::Fit::Fit);
        QCOMPARE(helm::parseFit(QStringLiteral("STRETCH")), helm::Fit::Stretch);
        QCOMPARE(helm::parseFit(QStringLiteral("center")), helm::Fit::Center);
        QCOMPARE(helm::parseFit(QStringLiteral("tile")), helm::Fit::Tile);
        QCOMPARE(helm::parseFit(QStringLiteral("cover")), helm::Fit::Fill);
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

    // Default mode is "world"; with no world resolvable, it falls back to the
    // flat base colour (abyss navy) and draws no image.
    void loadFallsBackToColorWhenNoWorld() {
        QTemporaryDir dir;
        const helm::Config cfg(dir.filePath(QStringLiteral("hede.conf")));
        const helm::Wallpaper w = helm::loadWallpaper(cfg);
        QVERIFY(!w.useImage);
        QCOMPARE(w.color, QColor(QStringLiteral("#0a1633"))); // abyss navy
        QCOMPARE(w.fit, helm::Fit::Fill);
    }

    // With a world on the search path, the default mode draws its scene and
    // adopts the world's fit ("cover" → Fill).
    void loadWorldScene() {
        QTemporaryDir worlds;
        const QString hdir = worlds.filePath(QStringLiteral("harbor"));
        QVERIFY(QDir().mkpath(hdir));
        QFile img(QDir(hdir).filePath(QStringLiteral("wallpaper.png")));
        QVERIFY(img.open(QIODevice::WriteOnly));
        img.write("x");
        img.close();
        QFile yaml(QDir(hdir).filePath(QStringLiteral("theme.yaml")));
        QVERIFY(yaml.open(QIODevice::WriteOnly));
        yaml.write("schema: helm.world/0.1\nid: harbor\nwallpaper_art:\n  image: wallpaper.png\n  "
                   "fit: cover\n");
        yaml.close();
        qputenv("HELM_WORLDS_DIR", worlds.path().toLocal8Bit());

        QTemporaryDir cfgdir;
        const helm::Wallpaper w =
            helm::loadWallpaper(helm::Config(cfgdir.filePath(QStringLiteral("hede.conf"))));
        QVERIFY(w.useImage);
        QCOMPARE(w.imagePath, img.fileName());
        QCOMPARE(w.fit, helm::Fit::Fill); // cover
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
