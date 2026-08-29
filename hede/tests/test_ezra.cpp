// ezra-lib: the /proc parsers against string fixtures, and the process
// model's in-place row merge (rows must survive a refresh so view selection
// doesn't jump).
#include "processmodel.h"
#include "sampler.h"

#include <QtTest>

using namespace ezra;

class TestEzra : public QObject {
    Q_OBJECT
private slots:
    void procStat();
    void memInfo();
    void netDevSkipsLoopback();
    void diskStatsWholeDisksOnly();
    void pidStat();
    void pidStatEvilComm();
    void pidStatRejectsGarbage();
    void modelMergeKeepsRows();
};

void TestEzra::procStat() {
    const QByteArray text =
        "cpu  100 5 50 800 20 3 2 1 0 0\n"
        "cpu0 60 3 30 400 10 2 1 1 0 0\n"
        "cpu1 40 2 20 400 10 1 1 0 0 0\n"
        "intr 12345\n";
    CpuTimes total;
    QVector<CpuTimes> cores;
    QVERIFY(parseProcStat(text, &total, &cores));
    QCOMPARE(total.user, 100ULL);
    QCOMPARE(total.idle, 800ULL);
    QCOMPARE(total.total(), 981ULL);
    QCOMPARE(total.active(), 161ULL);
    QCOMPARE(cores.size(), 2);
    QCOMPARE(cores.at(1).user, 40ULL);
}

void TestEzra::memInfo() {
    const QByteArray text =
        "MemTotal:       16384000 kB\n"
        "MemFree:         1000000 kB\n"
        "MemAvailable:    8192000 kB\n"
        "SwapTotal:       4000000 kB\n"
        "SwapFree:        3000000 kB\n";
    const MemInfo mem = parseMemInfo(text);
    QCOMPARE(mem.totalKb, 16384000ULL);
    QCOMPARE(mem.availableKb, 8192000ULL);
    QCOMPARE(mem.swapTotalKb, 4000000ULL);
    QCOMPARE(mem.swapFreeKb, 3000000ULL);
}

void TestEzra::netDevSkipsLoopback() {
    const QByteArray text =
        "Inter-|   Receive                                                |  Transmit\n"
        " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed\n"
        "    lo: 9999999   100    0    0    0     0          0         0  9999999   100    0    0    0     0       0          0\n"
        "  eth0: 1000      10     0    0    0     0          0         0  2000      20     0    0    0     0       0          0\n"
        " wlan0: 500       5      0    0    0     0          0         0  700       7     0    0    0     0       0          0\n";
    const NetTotals net = parseNetDev(text);
    QCOMPARE(net.rxBytes, 1500ULL);
    QCOMPARE(net.txBytes, 2700ULL);
}

void TestEzra::diskStatsWholeDisksOnly() {
    const QByteArray text =
        "   8       0 sda 100 0 1000 50 200 0 2000 80 0 100 130\n"
        "   8       1 sda1 90 0 900 45 190 0 1900 75 0 90 120\n"
        " 259       0 nvme0n1 300 0 3000 60 400 0 4000 90 0 120 150\n"
        " 259       1 nvme0n1p1 290 0 2900 55 390 0 3900 85 0 110 140\n"
        "   7       0 loop0 10 0 100 1 0 0 0 0 0 1 1\n";
    const DiskTotals disk = parseDiskStats(text);
    QCOMPARE(disk.readSectors, 4000ULL);  // sda + nvme0n1 only
    QCOMPARE(disk.writeSectors, 6000ULL);
}

void TestEzra::pidStat() {
    const QByteArray text =
        "1234 (ezra) S 1 1234 1234 0 -1 4194304 100 0 0 0 "
        "500 250 0 0 20 0 4 0 12345 100000000 2048 "
        "18446744073709551615 1 1 0 0 0 0 0 0 0 0 0 0 17 0 0 0 0 0 0";
    ProcessSample p;
    QVERIFY(parsePidStat(text, 4096, &p));
    QCOMPARE(p.pid, 1234);
    QCOMPARE(p.name, QStringLiteral("ezra"));
    QCOMPARE(p.state, 'S');
    QCOMPARE(p.ppid, 1);
    QCOMPARE(p.utime, 500ULL);
    QCOMPARE(p.stime, 250ULL);
    QCOMPARE(p.rssBytes, 2048ULL * 4096ULL);
}

void TestEzra::pidStatEvilComm() {
    // comm may contain spaces and parentheses — fields anchor on the LAST ')'.
    const QByteArray text =
        "42 (evil (name) here) R 1 42 42 0 -1 4194304 1 0 0 0 "
        "7 3 0 0 20 0 1 0 100 1000 10 "
        "18446744073709551615 1 1 0 0 0 0 0 0 0 0 0 0 17 0 0 0 0 0 0";
    ProcessSample p;
    QVERIFY(parsePidStat(text, 4096, &p));
    QCOMPARE(p.pid, 42);
    QCOMPARE(p.name, QStringLiteral("evil (name) here"));
    QCOMPARE(p.state, 'R');
    QCOMPARE(p.utime, 7ULL);
    QCOMPARE(p.stime, 3ULL);
}

void TestEzra::pidStatRejectsGarbage() {
    ProcessSample p;
    QVERIFY(!parsePidStat("", 4096, &p));
    QVERIFY(!parsePidStat("not a stat line", 4096, &p));
    QVERIFY(!parsePidStat("12 (short) R 1 2", 4096, &p));
}

void TestEzra::modelMergeKeepsRows() {
    ProcessModel model;
    auto proc = [](int pid, const char *name, double cpu) {
        ProcessSample p;
        p.pid = pid;
        p.name = QString::fromLatin1(name);
        p.cpuPercent = cpu;
        return p;
    };

    model.setSamples({proc(1, "init", 0.0), proc(2, "ezra", 5.0), proc(3, "foot", 1.0)});
    QCOMPARE(model.rowCount(), 3);
    QCOMPARE(model.sampleAt(1)->pid, 2);

    // pid 2 updates in place, pid 3 dies, pid 4 appears.
    model.setSamples({proc(1, "init", 0.0), proc(2, "ezra", 9.5), proc(4, "sefe", 2.0)});
    QCOMPARE(model.rowCount(), 3);
    QCOMPARE(model.sampleAt(1)->pid, 2); // same row, not reshuffled
    QCOMPARE(model.sampleAt(1)->cpuPercent, 9.5);
    QCOMPARE(model.sampleAt(2)->pid, 4); // new pid appended at the end

    // Display formatting sanity.
    QCOMPARE(model.data(model.index(1, ProcessModel::Cpu), Qt::DisplayRole).toString(),
             QStringLiteral("9.5 %"));
    QCOMPARE(model.data(model.index(0, ProcessModel::Name), Qt::DisplayRole).toString(),
             QStringLiteral("init"));
}

QTEST_GUILESS_MAIN(TestEzra)
#include "test_ezra.moc"
