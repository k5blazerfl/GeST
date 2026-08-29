// ezra-lib — the sampling engine behind EzRA (docs/design/ezra.md), HeDE's
// task manager. Pure parsers over /proc text (unit-tested against fixtures)
// plus two stateful samplers that turn consecutive readings into rates:
// ProcessSampler (per-process CPU%/RSS) and SystemSampler (machine-wide CPU,
// memory, disk, network). Core-only — the Qt window sits on top.
#pragma once

#include <QByteArray>
#include <QHash>
#include <QString>
#include <QVector>

namespace ezra {

// One process, as read from /proc/<pid>/stat (+ uid from the dir owner).
// utime/stime are cumulative clock ticks; cpuPercent is filled in by
// ProcessSampler from the delta against the previous sample, as a share of
// the WHOLE machine (all cores = 100%), matching the OG Task Manager.
struct ProcessSample {
    int pid = 0;
    int ppid = 0;
    QString name;    // comm, without the parentheses
    QString cmdline; // full command line ('' for kernel threads)
    QString user;
    char state = '?';
    int nice = 0;
    int threads = 0;
    qulonglong utime = 0;
    qulonglong stime = 0;
    qulonglong rssBytes = 0;
    double cpuPercent = 0.0;
};

// One "cpu…" row of /proc/stat, in clock ticks.
struct CpuTimes {
    qulonglong user = 0, nice = 0, system = 0, idle = 0;
    qulonglong iowait = 0, irq = 0, softirq = 0, steal = 0;
    qulonglong total() const { return user + nice + system + idle + iowait + irq + softirq + steal; }
    qulonglong active() const { return total() - idle - iowait; }
};

struct MemInfo {
    qulonglong totalKb = 0, availableKb = 0;
    qulonglong swapTotalKb = 0, swapFreeKb = 0;
};

struct NetTotals {
    qulonglong rxBytes = 0, txBytes = 0;
};

struct DiskTotals {
    qulonglong readSectors = 0, writeSectors = 0; // 512-byte sectors
};

// --- pure parsers ---------------------------------------------------------

// /proc/stat: fills the aggregate "cpu" row into *total and one entry per
// "cpuN" row into perCore. Returns false if no aggregate row was found.
bool parseProcStat(const QByteArray &text, CpuTimes *total, QVector<CpuTimes> *perCore);

MemInfo parseMemInfo(const QByteArray &text);

// /proc/net/dev, summed over every interface except lo.
NetTotals parseNetDev(const QByteArray &text);

// /proc/diskstats, summed over whole physical disks only (sd*, nvme*n*,
// vd*, mmcblk*) — partitions would double-count their parent disk.
DiskTotals parseDiskStats(const QByteArray &text);

// /proc/<pid>/stat. comm may itself contain spaces and parentheses, so the
// fields are anchored on the LAST ')'. rss arrives in pages; pass the page
// size so the parser stays a pure function. Fills pid/name/state/ppid/
// nice/threads/utime/stime/rssBytes.
bool parsePidStat(const QByteArray &text, qulonglong pageSize, ProcessSample *out);

// "R" -> "Running", "Z" -> "Zombie", … for the Details Status column.
QString stateName(char state);

// --- stateful samplers ----------------------------------------------------

// Scans /proc and computes per-process CPU% from the tick delta since the
// previous call. The first call reports 0% for everything (no delta yet).
class ProcessSampler {
public:
    QVector<ProcessSample> sample();

private:
    QHash<int, qulonglong> prevTicks_; // pid -> utime+stime at last sample
    qulonglong prevTotal_ = 0;         // machine total ticks at last sample
    QHash<uint, QString> userCache_;   // uid -> name
};

// Machine-wide gauges; rates are per-second over the wall time since the
// previous call (zeros on the first call).
class SystemSampler {
public:
    struct Snapshot {
        double cpuPercent = 0.0;
        QVector<double> perCorePercent;
        MemInfo mem;
        double rxBytesPerSec = 0.0, txBytesPerSec = 0.0;
        double readBytesPerSec = 0.0, writeBytesPerSec = 0.0;
    };
    Snapshot sample();

private:
    bool primed_ = false;
    CpuTimes prevTotal_;
    QVector<CpuTimes> prevCores_;
    NetTotals prevNet_;
    DiskTotals prevDisk_;
    qint64 prevMonotonicMs_ = 0;
};

} // namespace ezra
