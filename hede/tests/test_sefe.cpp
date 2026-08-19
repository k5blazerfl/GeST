#include <QtTest>

#include <QDir>
#include <QFile>
#include <QStringList>
#include <QTemporaryDir>

#include "ops.h"
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

    void newFolderNameDisambiguates() {
        QCOMPARE(helm::sefe::newFolderName({}), QStringLiteral("New folder"));
        QCOMPARE(helm::sefe::newFolderName({QStringLiteral("New folder")}),
                 QStringLiteral("New folder (2)"));
        QCOMPARE(helm::sefe::newFolderName(
                     {QStringLiteral("New folder"), QStringLiteral("New folder (2)")}),
                 QStringLiteral("New folder (3)"));
    }

    void copyNameIsWindowsStyle() {
        // " - Copy" goes before the extension; folders have none.
        QCOMPARE(helm::sefe::copyName(QStringLiteral("Report.txt"), {}),
                 QStringLiteral("Report - Copy.txt"));
        QCOMPARE(helm::sefe::copyName(QStringLiteral("Work"), {}),
                 QStringLiteral("Work - Copy"));
        // dotfiles have no extension
        QCOMPARE(helm::sefe::copyName(QStringLiteral(".bashrc"), {}),
                 QStringLiteral(".bashrc - Copy"));
        // collisions escalate
        QCOMPARE(helm::sefe::copyName(QStringLiteral("Work"),
                                      {QStringLiteral("Work - Copy")}),
                 QStringLiteral("Work - Copy (2)"));
        QCOMPARE(helm::sefe::copyName(
                     QStringLiteral("a.txt"),
                     {QStringLiteral("a - Copy.txt"), QStringLiteral("a - Copy (2).txt")}),
                 QStringLiteral("a - Copy (3).txt"));
    }

    void copyAndMoveRecursively() {
        QTemporaryDir tmp;
        const QString root = tmp.path();
        // src/  ├─ file.txt   └─ sub/nested.txt
        QDir(root).mkpath(QStringLiteral("src/sub"));
        QFile a(root + "/src/file.txt");
        QVERIFY(a.open(QIODevice::WriteOnly));
        a.write("hello");
        a.close();
        QFile b(root + "/src/sub/nested.txt");
        QVERIFY(b.open(QIODevice::WriteOnly));
        b.write("deep");
        b.close();

        // copy → both trees exist
        QVERIFY(helm::sefe::copyRecursively(root + "/src", root + "/copy"));
        QVERIFY(QFile::exists(root + "/copy/file.txt"));
        QVERIFY(QFile::exists(root + "/copy/sub/nested.txt"));
        QVERIFY(QFile::exists(root + "/src/file.txt")); // source untouched

        // move → target exists, source gone
        QVERIFY(helm::sefe::moveItem(root + "/src", root + "/moved"));
        QVERIFY(QFile::exists(root + "/moved/sub/nested.txt"));
        QVERIFY(!QFile::exists(root + "/src"));
    }

    void compressTargetNaming() {
        // single item → its stem; folders & multi-dot names handled
        QCOMPARE(helm::sefe::compressTargetName({QStringLiteral("/x/report.pdf")}, {}),
                 QStringLiteral("report.zip"));
        QCOMPARE(helm::sefe::compressTargetName({QStringLiteral("/x/Photos")}, {}),
                 QStringLiteral("Photos.zip"));
        // several items → Archive.zip
        QCOMPARE(helm::sefe::compressTargetName(
                     {QStringLiteral("/x/a.txt"), QStringLiteral("/x/b.txt")}, {}),
                 QStringLiteral("Archive.zip"));
        // collisions escalate
        QCOMPARE(helm::sefe::compressTargetName({QStringLiteral("/x/Photos")},
                                                {QStringLiteral("Photos.zip")}),
                 QStringLiteral("Photos (2).zip"));
    }

    void windowsExecutableByExtension() {
        QVERIFY(helm::sefe::isWindowsExecutable(QStringLiteral("/x/setup.exe")));
        QVERIFY(helm::sefe::isWindowsExecutable(QStringLiteral("/x/GAME.EXE"))); // case-insensitive
        QVERIFY(helm::sefe::isWindowsExecutable(QStringLiteral("/x/pkg.msi")));
        QVERIFY(helm::sefe::isWindowsExecutable(QStringLiteral("/x/app.lnk")));
        QVERIFY(helm::sefe::isWindowsExecutable(QStringLiteral("/x/run.bat")));
        QVERIFY(!helm::sefe::isWindowsExecutable(QStringLiteral("/x/notes.txt")));
        QVERIFY(!helm::sefe::isWindowsExecutable(QStringLiteral("/x/folder")));
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
