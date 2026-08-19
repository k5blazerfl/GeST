#include <QtTest>

#include <QDir>
#include <QFile>
#include <QTemporaryDir>

#include "holdcore.h"

class TestHoldCore : public QObject {
    Q_OBJECT
private slots:
    void isArchiveByExtension() {
        QVERIFY(helm::hold::isArchive(QStringLiteral("/x/a.zip")));
        QVERIFY(helm::hold::isArchive(QStringLiteral("/x/A.ZIP"))); // case-insensitive
        QVERIFY(helm::hold::isArchive(QStringLiteral("/x/a.tar.gz")));
        QVERIFY(helm::hold::isArchive(QStringLiteral("/x/a.7z")));
        QVERIFY(helm::hold::isArchive(QStringLiteral("/x/comic.cbz")));
        QVERIFY(!helm::hold::isArchive(QStringLiteral("/x/notes.txt")));
        QVERIFY(!helm::hold::isArchive(QStringLiteral("/x/folder")));
    }

    void safeJoinGuardsAgainstZipSlip() {
        const QString base = QStringLiteral("/tmp/out");
        QCOMPARE(helm::hold::safeJoin(base, QStringLiteral("sub/a.txt")),
                 QStringLiteral("/tmp/out/sub/a.txt"));
        // "../" escaping the destination is rejected
        QVERIFY(helm::hold::safeJoin(base, QStringLiteral("../evil")).isEmpty());
        QVERIFY(helm::hold::safeJoin(base, QStringLiteral("a/../../evil")).isEmpty());
        // an absolute entry path is re-rooted under base, never honoured as-is
        QCOMPARE(helm::hold::safeJoin(base, QStringLiteral("/etc/passwd")),
                 QStringLiteral("/tmp/out/etc/passwd"));
    }

    // create → list → extract round-trip through libarchive (zip).
    void zipRoundTrip() {
        QTemporaryDir tmp;
        const QString root = tmp.path();
        QVERIFY(QDir(root).mkpath(QStringLiteral("src/sub")));
        writeFile(root + "/src/a.txt", "hello");
        writeFile(root + "/src/sub/b.txt", "deep");

        const QString zip = root + "/out.zip";
        const auto cr = helm::hold::create({root + "/src/a.txt", root + "/src/sub"}, zip);
        QVERIFY2(cr.ok, qPrintable(cr.error));
        QVERIFY(QFile::exists(zip));

        const auto listed = helm::hold::list(zip);
        QVERIFY2(listed.ok, qPrintable(listed.error));
        QStringList names;
        qint64 aSize = -1;
        for (const auto &e : listed.entries) {
            names << e.path;
            if (e.path == QLatin1String("a.txt"))
                aSize = e.size;
        }
        QVERIFY(names.contains(QStringLiteral("a.txt")));
        QVERIFY(names.contains(QStringLiteral("sub/b.txt")));
        QCOMPARE(aSize, qint64(5)); // "hello"

        const auto ex = helm::hold::extractAll(zip, root + "/ex");
        QVERIFY2(ex.ok, qPrintable(ex.error));
        QCOMPARE(readFile(root + "/ex/a.txt"), QByteArray("hello"));
        QCOMPARE(readFile(root + "/ex/sub/b.txt"), QByteArray("deep"));

        // single-entry extract pulls only that file
        const auto one = helm::hold::extract(zip, QStringLiteral("a.txt"), root + "/ex2");
        QVERIFY2(one.ok, qPrintable(one.error));
        QVERIFY(QFile::exists(root + "/ex2/a.txt"));
        QVERIFY(!QFile::exists(root + "/ex2/sub/b.txt"));
        // a missing entry errors
        QVERIFY(!helm::hold::extract(zip, QStringLiteral("nope.txt"), root + "/ex3").ok);
    }

    // the tar+gzip write path also round-trips.
    void tarGzRoundTrip() {
        QTemporaryDir tmp;
        const QString root = tmp.path();
        writeFile(root + "/note.txt", "tar me");
        const QString tgz = root + "/out.tar.gz";
        QVERIFY2(helm::hold::create({root + "/note.txt"}, tgz).ok, "create tar.gz");
        const auto listed = helm::hold::list(tgz);
        QVERIFY(listed.ok);
        QCOMPARE(listed.entries.size(), 1);
        QCOMPARE(listed.entries.first().path, QStringLiteral("note.txt"));
        QVERIFY(helm::hold::extractAll(tgz, root + "/ex").ok);
        QCOMPARE(readFile(root + "/ex/note.txt"), QByteArray("tar me"));
    }

    void listErrorsOnNonArchive() {
        QTemporaryDir tmp;
        writeFile(tmp.path() + "/plain.txt", "not an archive");
        const auto listed = helm::hold::list(tmp.path() + "/plain.txt");
        QVERIFY(!listed.ok);
        QVERIFY(!listed.error.isEmpty());
        QVERIFY(!helm::hold::list(tmp.path() + "/missing.zip").ok);
    }

private:
    static void writeFile(const QString &path, const QByteArray &data) {
        QFile f(path);
        QVERIFY(f.open(QIODevice::WriteOnly));
        f.write(data);
    }
    static QByteArray readFile(const QString &path) {
        QFile f(path);
        return f.open(QIODevice::ReadOnly) ? f.readAll() : QByteArray();
    }
};

QTEST_MAIN(TestHoldCore)
#include "test_holdcore.moc"
