// ezra-lib: the /proc parsers against string fixtures, and the process
// model's in-place row merge (rows must survive a refresh so view selection
// doesn't jump).
#include "processmodel.h"
#include "sampler.h"
#include "sensors.h"
#include "services.h"
#include "usermodel.h"

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
    void stateNames();
    void pidStatEvilComm();
    void pidStatRejectsGarbage();
    void modelMergeKeepsRows();
    void userRollup();
    void serviceModelStatus();
    void sensorMath();
    void cgroupParse();
    void fdinfoDrmParse();
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
    QCOMPARE(p.nice, 0);
    QCOMPARE(p.threads, 4);
    QCOMPARE(p.rssBytes, 2048ULL * 4096ULL);
}

void TestEzra::stateNames() {
    QCOMPARE(stateName('R'), QStringLiteral("Running"));
    QCOMPARE(stateName('S'), QStringLiteral("Sleeping"));
    QCOMPARE(stateName('Z'), QStringLiteral("Zombie"));
    QCOMPARE(stateName('I'), QStringLiteral("Idle"));
    QCOMPARE(stateName('?'), QStringLiteral("?")); // unknown passes through
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

void TestEzra::userRollup() {
    auto proc = [](const char *user, double cpu, qulonglong rss) {
        ProcessSample p;
        p.user = QString::fromLatin1(user);
        p.cpuPercent = cpu;
        p.rssBytes = rss;
        return p;
    };
    const QVector<UserRollup> rollups = rollupByUser(
        {proc("root", 1.0, 100), proc("charron", 2.5, 200), proc("root", 0.5, 300)});
    QCOMPARE(rollups.size(), 2); // sorted by name: charron, root
    QCOMPARE(rollups.at(0).user, QStringLiteral("charron"));
    QCOMPARE(rollups.at(0).processes, 1);
    QCOMPARE(rollups.at(1).user, QStringLiteral("root"));
    QCOMPARE(rollups.at(1).processes, 2);
    QCOMPARE(rollups.at(1).cpuPercent, 1.5);
    QCOMPARE(rollups.at(1).rssBytes, 400ULL);

    UserModel model;
    model.setRollups(rollups);
    QCOMPARE(model.rowCount(), 2);
    QCOMPARE(model.data(model.index(1, UserModel::Cpu), Qt::DisplayRole).toString(),
             QStringLiteral("1.5 %"));
}

void TestEzra::serviceModelStatus() {
    UnitInfo running;
    running.name = QStringLiteral("sshd.service");
    running.loadState = QStringLiteral("loaded");
    running.activeState = QStringLiteral("active");
    running.subState = QStringLiteral("running");
    UnitInfo masked;
    masked.name = QStringLiteral("old.service");
    masked.loadState = QStringLiteral("masked");

    ServiceModel model;
    model.setServices({running, masked});
    QCOMPARE(model.rowCount(), 2);
    QCOMPARE(model.data(model.index(0, ServiceModel::Status), Qt::DisplayRole).toString(),
             QStringLiteral("active (running)"));
    QCOMPARE(model.data(model.index(1, ServiceModel::Status), Qt::DisplayRole).toString(),
             QStringLiteral("masked"));
    QCOMPARE(model.serviceAt(0)->name, QStringLiteral("sshd.service"));
}

void TestEzra::sensorMath() {
    TempReading hottest;
    QVERIFY(!hottestOf({}, &hottest));
    QVERIFY(hottestOf({{QStringLiteral("k10temp"), QStringLiteral("Tctl"), 62.5},
                       {QStringLiteral("amdgpu"), QStringLiteral("edge"), 71.0},
                       {QStringLiteral("nvme"), QStringLiteral("temp1"), 40.0}},
                      &hottest));
    QCOMPARE(hottest.chip, QStringLiteral("amdgpu"));
    QCOMPARE(hottest.degC, 71.0);

    // 10 J over 2 s = 5 W.
    QCOMPARE(wattsFromEnergyDelta(1'000'000, 11'000'000, 2000), 5.0);
    QCOMPARE(wattsFromEnergyDelta(11'000'000, 1'000'000, 2000), 0.0); // wrap → skip
    QCOMPARE(wattsFromEnergyDelta(1, 2, 0), 0.0);                     // no elapsed time
}

void TestEzra::cgroupParse() {
    QCOMPARE(parseCgroup("0::/user.slice/user-1000.slice/session-2.scope\n"),
             QStringLiteral("/user.slice/user-1000.slice/session-2.scope"));
    // Legacy v1 lines are ignored; only the v2 "0::" line counts.
    QCOMPARE(parseCgroup("12:cpu,cpuacct:/foo\n0::/bar\n"), QStringLiteral("/bar"));
    QCOMPARE(parseCgroup("12:cpu,cpuacct:/foo\n"), QString());
    QCOMPARE(parseCgroup(""), QString());
}

void TestEzra::fdinfoDrmParse() {
    DrmClient client;
    QVERIFY(parseFdinfoDrm("pos:\t0\nflags:\t02100002\n"
                           "drm-driver:\tamdgpu\n"
                           "drm-client-id:\t42\n"
                           "drm-engine-gfx:\t123456789 ns\n"
                           "drm-engine-compute:\t1000 ns\n",
                           &client));
    QCOMPARE(client.clientId, 42ULL);
    QCOMPARE(client.engineNs, 123457789ULL); // gfx + compute

    QVERIFY(!parseFdinfoDrm("pos:\t0\nflags:\t02\n", &client)); // not a DRM fd
}

QTEST_GUILESS_MAIN(TestEzra)
#include "test_ezra.moc"
