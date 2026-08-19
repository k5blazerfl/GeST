#include <QtTest>

#include <QDir>
#include <QStringList>
#include <QTemporaryDir>

#include "sefe.h"

class TestSefe : public QObject {
    Q_OBJECT
private slots:
    void initialDirFollowsHome() {
        qputenv("HOME", "/home/tester");
        QCOMPARE(helm::sefe::initialDir(), QStringLiteral("/home/tester"));
    }

    void windowTitleNamesTheFolder() {
        qputenv("HOME", "/home/tester");
        // Home gets the friendly label.
        QCOMPARE(helm::sefe::windowTitle(QStringLiteral("/home/tester")),
                 QStringLiteral("Home — Seahorse"));
        // Any other dir uses its base name.
        QCOMPARE(helm::sefe::windowTitle(QStringLiteral("/home/tester/Documents")),
                 QStringLiteral("Documents — Seahorse"));
        // The filesystem root has no base name → show the path.
        QCOMPARE(helm::sefe::windowTitle(QStringLiteral("/")),
                 QStringLiteral("/ — Seahorse"));
    }

    void breadcrumbsAreHomeAware() {
        qputenv("HOME", "/home/tester");
        auto labels = [](const QList<helm::sefe::Crumb> &cs) {
            QStringList l;
            for (const auto &c : cs)
                l << c.label;
            return l;
        };
        // Under home → starts at "Home".
        const auto home = helm::sefe::breadcrumbs(QStringLiteral("/home/tester"));
        QCOMPARE(labels(home), QStringList{QStringLiteral("Home")});
        QCOMPARE(home.first().path, QStringLiteral("/home/tester"));

        const auto docs = helm::sefe::breadcrumbs(QStringLiteral("/home/tester/Documents/Work"));
        QCOMPARE(labels(docs), (QStringList{"Home", "Documents", "Work"}));
        QCOMPARE(docs.last().path, QStringLiteral("/home/tester/Documents/Work"));
        QCOMPARE(docs[1].path, QStringLiteral("/home/tester/Documents")); // mid crumb navigates

        // Outside home → starts at "/".
        const auto etc = helm::sefe::breadcrumbs(QStringLiteral("/etc/xdg"));
        QCOMPARE(labels(etc), (QStringList{"/", "etc", "xdg"}));
        QCOMPARE(etc[1].path, QStringLiteral("/etc"));

        // Root itself → a single "/" crumb.
        const auto root = helm::sefe::breadcrumbs(QStringLiteral("/"));
        QCOMPARE(labels(root), QStringList{QStringLiteral("/")});

        // A sibling of home is NOT treated as under home.
        const auto sibling = helm::sefe::breadcrumbs(QStringLiteral("/home/tester2"));
        QCOMPARE(labels(sibling), (QStringList{"/", "home", "tester2"}));
    }

    void parentDirWalksUp() {
        QCOMPARE(helm::sefe::parentDir(QStringLiteral("/home/tester/Documents")),
                 QStringLiteral("/home/tester"));
        QCOMPARE(helm::sefe::parentDir(QStringLiteral("/home")), QStringLiteral("/"));
        QCOMPARE(helm::sefe::parentDir(QStringLiteral("/")), QStringLiteral("/")); // clamped
    }

    void normalizePathResolves() {
        qputenv("HOME", "/home/tester");
        QCOMPARE(helm::sefe::normalizePath(QStringLiteral("~")), QStringLiteral("/home/tester"));
        QCOMPARE(helm::sefe::normalizePath(QStringLiteral("~/Documents")),
                 QStringLiteral("/home/tester/Documents"));
        QCOMPARE(helm::sefe::normalizePath(QStringLiteral("/etc/../usr")),
                 QStringLiteral("/usr")); // cleaned
        // relative resolves against base
        QCOMPARE(helm::sefe::normalizePath(QStringLiteral("Work"), QStringLiteral("/home/tester/Documents")),
                 QStringLiteral("/home/tester/Documents/Work"));
        // trims and empty → base
        QCOMPARE(helm::sefe::normalizePath(QStringLiteral("  /tmp  ")), QStringLiteral("/tmp"));
        QCOMPARE(helm::sefe::normalizePath(QString(), QStringLiteral("/var")), QStringLiteral("/var"));
    }

    void placesIncludeHomeAndComputer() {
        // Point HOME + XDG at a temp tree so the set is deterministic.
        QTemporaryDir tmp;
        qputenv("HOME", tmp.path().toUtf8());
        qputenv("XDG_CONFIG_HOME", (tmp.path() + "/.config").toUtf8());
        QDir(tmp.path()).mkpath(QStringLiteral("Documents"));
        const auto ps = helm::sefe::places();
        QStringList names;
        for (const auto &p : ps)
            names << p.name;
        QVERIFY(names.contains(QStringLiteral("Home")));
        QVERIFY(names.contains(QStringLiteral("Computer")));
        QCOMPARE(ps.first().name, QStringLiteral("Home"));
        QCOMPARE(ps.first().path, tmp.path());
        QCOMPARE(ps.last().path, QStringLiteral("/"));
        qunsetenv("XDG_CONFIG_HOME");
    }
};

QTEST_MAIN(TestSefe)
#include "test_sefe.moc"
