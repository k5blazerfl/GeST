#include <QtTest>

#include "search.h"

class TestSearch : public QObject {
    Q_OBJECT
  private slots:
    void subsequenceOnly() {
        QVERIFY(helm::fuzzyScore(QStringLiteral("Firefox"), QStringLiteral("ffx")) >= 0);
        QVERIFY(helm::fuzzyScore(QStringLiteral("Firefox"), QStringLiteral("xyz")) < 0);
        QCOMPARE(helm::fuzzyScore(QStringLiteral("anything"), QString()), 0);
    }

    void prefixBeatsMidword() {
        // "term" as a prefix of "Terminal" should outscore "term" buried in a name.
        const int pref = helm::fuzzyScore(QStringLiteral("Terminal"), QStringLiteral("term"));
        const int mid = helm::fuzzyScore(QStringLiteral("xterminator"), QStringLiteral("term"));
        QVERIFY(pref > mid);
    }

    void consecutiveBeatsScattered() {
        const int consec = helm::fuzzyScore(QStringLiteral("abc"), QStringLiteral("abc"));
        const int scattered = helm::fuzzyScore(QStringLiteral("axbxc"), QStringLiteral("abc"));
        QVERIFY(consec > scattered);
    }

    void rankOrdersByScore() {
        QVector<helm::DesktopEntry> es;
        helm::DesktopEntry a;
        a.name = QStringLiteral("Terminal");
        a.id = QStringLiteral("terminal");
        helm::DesktopEntry b;
        b.name = QStringLiteral("File Manager");
        b.id = QStringLiteral("files");
        helm::DesktopEntry c;
        c.name = QStringLiteral("Settings");
        c.id = QStringLiteral("settings");
        es << b << c << a;
        const QVector<helm::DesktopEntry> r = helm::rankEntries(es, QStringLiteral("term"));
        QCOMPARE(r.size(), 1);
        QCOMPARE(r.first().name, QStringLiteral("Terminal"));
    }

    void matchingExecutablesRanksAndCaps() {
        const QStringList all = {QStringLiteral("ls"), QStringLiteral("lsblk"),
                                 QStringLiteral("grep"), QStringLiteral("lsof")};
        const QStringList m = helm::matchingExecutables(all, QStringLiteral("ls"), 2);
        QCOMPARE(m.size(), 2);                       // capped
        QVERIFY(!m.contains(QStringLiteral("grep"))); // no subsequence match
        QCOMPARE(m.first(), QStringLiteral("ls"));    // exact prefix ranks first
        QVERIFY(helm::matchingExecutables(all, QString(), 8).isEmpty()); // empty query → nothing
    }
};

QTEST_MAIN(TestSearch)
#include "test_search.moc"
