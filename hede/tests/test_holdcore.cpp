#include <QtTest>

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QProcess>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QThread>

#include <filesystem>
#include <system_error>

#include "holdcore.h"
#include "job.h"

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

    // A1: the symlink-escape guard (pure decision logic, like safeJoin).
    void symlinkEscapeGuard() {
        const QString base = QStringLiteral("/tmp/out");
        // an absolute target always leaves the sandbox
        QVERIFY(helm::hold::symlinkEscapes(base, QStringLiteral("link"),
                                           QStringLiteral("/etc/passwd")));
        // a relative target that climbs out escapes
        QVERIFY(helm::hold::symlinkEscapes(base, QStringLiteral("sub/link"),
                                           QStringLiteral("../../etc")));
        // contained relative targets are fine
        QVERIFY(!helm::hold::symlinkEscapes(base, QStringLiteral("link"),
                                            QStringLiteral("a.txt")));
        QVERIFY(!helm::hold::symlinkEscapes(base, QStringLiteral("sub/link"),
                                            QStringLiteral("../a.txt"))); // → /tmp/out/a.txt
        // a target resolving exactly to the base is contained, not an escape
        QVERIFY(!helm::hold::symlinkEscapes(base, QStringLiteral("sub/link"),
                                            QStringLiteral("..")));
        // an empty target points nowhere — nothing to escape
        QVERIFY(!helm::hold::symlinkEscapes(base, QStringLiteral("link"), QString()));
    }

    // A1: on extract, an escaping symlink is refused (and reported), a contained one
    // is kept, and extraction of the rest still succeeds.
    void symlinkEscapeGuardOnExtract() {
        QTemporaryDir tmp;
        const QString root = tmp.path();
        QVERIFY(QDir(root).mkpath(QStringLiteral("src")));
        writeFile(root + "/src/a.txt", "hi");

        namespace fs = std::filesystem;
        std::error_code ec;
        fs::create_symlink("/etc/passwd", fs::path((root + "/src/evil").toStdString()), ec);
        fs::create_symlink("a.txt", fs::path((root + "/src/ok").toStdString()), ec);
        QVERIFY2(!ec, "could not create the test symlinks");

        // Pack with system tar (it preserves symlinks); hold::create can't yet.
        QProcess tar;
        tar.setWorkingDirectory(root + "/src");
        tar.start(QStringLiteral("tar"),
                  {QStringLiteral("cf"), root + "/s.tar", QStringLiteral("a.txt"),
                   QStringLiteral("evil"), QStringLiteral("ok")});
        if (!tar.waitForStarted(2000))
            QSKIP("tar not available to build the symlink fixture");
        QVERIFY(tar.waitForFinished(5000));
        QCOMPARE(tar.exitCode(), 0);

        const auto ex = helm::hold::extractAll(root + "/s.tar", root + "/ex");
        QVERIFY2(ex.ok, qPrintable(ex.error));                  // the rest still extracts
        QCOMPARE(readFile(root + "/ex/a.txt"), QByteArray("hi"));
        QVERIFY(QFileInfo(root + "/ex/ok").isSymLink());        // safe symlink kept
        QVERIFY(ex.skipped.contains(QStringLiteral("evil")));   // escaping one reported
        QVERIFY(!QFileInfo(root + "/ex/evil").isSymLink());     // ...and never created
    }

    // A1: the zip-bomb caps — extraction past a byte or entry limit is refused,
    // and a generous cap extracts normally.
    void extractionSizeCapRefuses() {
        QTemporaryDir tmp;
        const QString root = tmp.path();
        writeFile(root + "/big.txt", QByteArray(4096, 'x'));
        const QString zip = root + "/b.zip";
        QVERIFY(helm::hold::create({root + "/big.txt"}, zip).ok);

        helm::hold::Limits limits;
        limits.maxTotalBytes = 1024; // a 4 KiB payload against a 1 KiB cap → refuse
        const auto ex = helm::hold::extractAll(zip, root + "/ex", {}, limits);
        QVERIFY(!ex.ok);
        QVERIFY(ex.error.contains(QStringLiteral("limit")));

        QVERIFY(helm::hold::extractAll(zip, root + "/ex2", {}, {}).ok); // default cap is generous
        QCOMPARE(readFile(root + "/ex2/big.txt").size(), 4096);
    }

    void extractionEntryCapRefuses() {
        QTemporaryDir tmp;
        const QString root = tmp.path();
        QStringList files;
        for (int i = 0; i < 5; ++i) {
            const QString f = root + QStringLiteral("/f%1.txt").arg(i);
            writeFile(f, "x");
            files << f;
        }
        const QString zip = root + "/e.zip";
        QVERIFY(helm::hold::create(files, zip).ok);

        helm::hold::Limits limits;
        limits.maxEntries = 3; // 5 entries > 3 → refuse
        const auto ex = helm::hold::extractAll(zip, root + "/ex", {}, limits);
        QVERIFY(!ex.ok);
        QVERIFY(ex.error.contains(QStringLiteral("entry")));
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

    // A0: multi-select extract — a subset of entries in one pass; a requested
    // directory pulls in its descendants, unrequested siblings are left out.
    void extractEntriesSubset() {
        QTemporaryDir tmp;
        const QString root = tmp.path();
        QVERIFY(QDir(root).mkpath(QStringLiteral("src/sub")));
        writeFile(root + "/src/a.txt", "A");
        writeFile(root + "/src/b.txt", "B");
        writeFile(root + "/src/sub/c.txt", "C");
        const QString zip = root + "/x.zip";
        QVERIFY(helm::hold::create({root + "/src"}, zip).ok);

        const auto r = helm::hold::extractEntries(
            zip, {QStringLiteral("src/a.txt"), QStringLiteral("src/sub")}, root + "/ex");
        QVERIFY2(r.ok, qPrintable(r.error));
        QVERIFY(QFile::exists(root + "/ex/src/a.txt"));
        QVERIFY(QFile::exists(root + "/ex/src/sub/c.txt")); // dir pulled its descendant
        QVERIFY(!QFile::exists(root + "/ex/src/b.txt"));     // not requested
    }

    // A0: the synchronous Progress hook — step() reports per top-level entry, and
    // cancel() stops create() early and removes the partial output.
    void progressAndCancelSync() {
        QTemporaryDir tmp;
        const QString root = tmp.path();
        QStringList files;
        for (int i = 0; i < 5; ++i) {
            const QString f = root + QStringLiteral("/f%1.txt").arg(i);
            writeFile(f, QByteArray(64, 'x'));
            files << f;
        }
        int steps = 0;
        qint64 lastDone = 0, lastTotal = -2;
        helm::hold::Progress p;
        p.step = [&](qint64 d, qint64 t, const QString &) {
            ++steps;
            lastDone = d;
            lastTotal = t;
        };
        QVERIFY(helm::hold::create(files, root + "/p.zip", p).ok);
        QCOMPARE(steps, 5);
        QCOMPARE(lastDone, qint64(5));
        QCOMPARE(lastTotal, qint64(5));

        // Cancel after two entries → cancelled, no partial archive left behind.
        int seen = 0;
        helm::hold::Progress cp;
        cp.step = [&](qint64, qint64, const QString &) { ++seen; };
        cp.cancelled = [&] { return seen >= 2; };
        const QString cancelled = root + "/c.zip";
        const auto cr = helm::hold::create(files, cancelled, cp);
        QVERIFY(!cr.ok);
        QCOMPARE(cr.error, QStringLiteral("cancelled"));
        QVERIFY(!QFile::exists(cancelled));
    }

    // A0: hold::Job runs the op off-thread and emits progress() + finished().
    void jobExtractAsync() {
        QTemporaryDir tmp;
        const QString root = tmp.path();
        QVERIFY(QDir(root).mkpath(QStringLiteral("s")));
        writeFile(root + "/s/a.txt", "A");
        writeFile(root + "/s/b.txt", "B");
        const QString zip = root + "/j.zip";
        QVERIFY(helm::hold::create({root + "/s"}, zip).ok);

        helm::hold::Job job(QStringLiteral("Extract"));
        QSignalSpy prog(&job, &helm::hold::Job::progress);
        QSignalSpy fin(&job, &helm::hold::Job::finished);
        const QString dest = root + "/out";
        job.run([zip, dest](const helm::hold::Progress &p) {
            return helm::hold::extractAll(zip, dest, p);
        });
        QVERIFY(fin.wait(5000));
        QCOMPARE(fin.count(), 1);
        const auto res = qvariant_cast<helm::hold::Result>(fin.at(0).at(0));
        QVERIFY2(res.ok, qPrintable(res.error));
        QVERIFY(prog.count() >= 1);
        QVERIFY(QFile::exists(dest + "/s/a.txt"));
    }

    // A0: cancel() stops a running Job and it finishes "cancelled".
    void jobCancelStops() {
        helm::hold::Job job(QStringLiteral("busy"));
        QSignalSpy fin(&job, &helm::hold::Job::finished);
        job.run([](const helm::hold::Progress &p) -> helm::hold::Result {
            for (int i = 0; i < 100000; ++i) {
                if (p.cancelled && p.cancelled()) {
                    helm::hold::Result r;
                    r.error = QStringLiteral("cancelled");
                    return r;
                }
                if (p.step)
                    p.step(i, -1, QStringLiteral("x"));
                QThread::msleep(1);
            }
            helm::hold::Result r;
            r.ok = true;
            return r;
        });
        QTest::qWait(40);
        job.cancel();
        QVERIFY(fin.wait(5000));
        const auto res = qvariant_cast<helm::hold::Result>(fin.at(0).at(0));
        QVERIFY(!res.ok);
        QCOMPARE(res.error, QStringLiteral("cancelled"));
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
