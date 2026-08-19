#include <QtTest>

#include <QDir>
#include <QFile>
#include <QTemporaryDir>

#include "world.h"

class TestWorld : public QObject {
    Q_OBJECT
private slots:
    void parsesScalarsAndSections() {
        const QString doc = QStringLiteral(
            "schema: helm.world/0.1\n"
            "id: harbor\n"
            "name: Harbor\n"
            "# a comment line\n"
            "accent: '#3aa6c4'\n"
            "bar:\n"
            "  style: glass\n"
            "  tint: cool\n"
            "wallpaper_art:\n"
            "  image: wallpaper.png\n"
            "  fit: cover\n"
            "credit:\n"
            "  art: local\n");
        const helm::World w = helm::parseWorldYaml(doc, QStringLiteral("/base"));
        QVERIFY(w.valid());
        QCOMPARE(w.id, QStringLiteral("harbor"));
        QCOMPARE(w.name, QStringLiteral("Harbor"));
        QCOMPARE(w.accent, QStringLiteral("#3aa6c4")); // quotes stripped, '#' kept
        QCOMPARE(w.barStyle, QStringLiteral("glass"));
        QCOMPARE(w.barTint, QStringLiteral("cool"));
        QCOMPARE(w.wallpaperImage, QStringLiteral("wallpaper.png"));
        QCOMPARE(w.wallpaperFit, QStringLiteral("cover"));
    }

    // A nested key name shared across sections must resolve under its own
    // section, not a sibling (e.g. bar has no "image").
    void sectionScoping() {
        const helm::World w = helm::parseWorldYaml(
            QStringLiteral("id: x\nbar:\n  style: solid\nwallpaper_art:\n  image: w.png\n"));
        QCOMPARE(w.barStyle, QStringLiteral("solid"));
        QCOMPARE(w.wallpaperImage, QStringLiteral("w.png"));
    }

    void invalidWhenNoId() {
        const helm::World w = helm::parseWorldYaml(QStringLiteral("name: Nameless\naccent: '#fff'\n"));
        QVERIFY(!w.valid());
    }

    void wallpaperPathRequiresExistingFile() {
        QTemporaryDir dir;
        helm::World w;
        w.baseDir = dir.path();
        w.wallpaperImage = QStringLiteral("scene.png");
        QCOMPARE(w.wallpaperPath(), QString()); // missing → empty
        QFile f(QDir(dir.path()).filePath(QStringLiteral("scene.png")));
        QVERIFY(f.open(QIODevice::WriteOnly));
        f.write("x");
        f.close();
        QCOMPARE(w.wallpaperPath(), f.fileName());
    }

    void loadWorldFromSearchPath() {
        QTemporaryDir worlds;
        const QString hdir = QDir(worlds.path()).filePath(QStringLiteral("harbor"));
        QVERIFY(QDir().mkpath(hdir));
        QFile y(QDir(hdir).filePath(QStringLiteral("theme.yaml")));
        QVERIFY(y.open(QIODevice::WriteOnly));
        y.write("id: harbor\nname: Harbor\naccent: '#3aa6c4'\n");
        y.close();

        qputenv("HELM_WORLDS_DIR", worlds.path().toLocal8Bit());
        const helm::World w = helm::loadWorld(QStringLiteral("harbor"));
        qunsetenv("HELM_WORLDS_DIR");
        QVERIFY(w.valid());
        QCOMPARE(w.accent, QStringLiteral("#3aa6c4"));
        QCOMPARE(w.baseDir, hdir);
    }

    void loadWorldMissingIsInvalid() {
        QTemporaryDir worlds; // empty
        qputenv("HELM_WORLDS_DIR", worlds.path().toLocal8Bit());
        const helm::World w = helm::loadWorld(QStringLiteral("nope"));
        qunsetenv("HELM_WORLDS_DIR");
        QVERIFY(!w.valid());
    }

    void listWorldsSortedByName() {
        QTemporaryDir worlds;
        auto make = [&](const QString &id, const QString &name) {
            const QString d = QDir(worlds.path()).filePath(id);
            QDir().mkpath(d);
            QFile y(QDir(d).filePath(QStringLiteral("theme.yaml")));
            QVERIFY(y.open(QIODevice::WriteOnly));
            y.write(QStringLiteral("id: %1\nname: %2\naccent: '#3aa6c4'\n").arg(id, name).toUtf8());
        };
        make(QStringLiteral("harbor"), QStringLiteral("Harbor"));
        make(QStringLiteral("emberforge"), QStringLiteral("Emberforge"));
        make(QStringLiteral("bogus"), QString()); // no id? has id; keep valid
        qputenv("HELM_WORLDS_DIR", worlds.path().toLocal8Bit());
        const QList<helm::World> ws = helm::listWorlds();
        qunsetenv("HELM_WORLDS_DIR");
        // sorted by display name: Emberforge, Harbor, (bogus has empty name → first)
        QVERIFY(ws.size() >= 2);
        const int ie = [&] { for (int i = 0; i < ws.size(); ++i) if (ws[i].id == "emberforge") return i; return -1; }();
        const int ih = [&] { for (int i = 0; i < ws.size(); ++i) if (ws[i].id == "harbor") return i; return -1; }();
        QVERIFY(ie >= 0 && ih >= 0);
        QVERIFY(ie < ih); // Emberforge before Harbor
    }
};

QTEST_MAIN(TestWorld)
#include "test_world.moc"
