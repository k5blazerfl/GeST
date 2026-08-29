#include "sampler.h"

#include <QDir>
#include <QElapsedTimer>
#include <QFile>
#include <QRegularExpression>

#include <algorithm>

#include <pwd.h>
#include <sys/stat.h>
#include <unistd.h>

namespace ezra {

namespace {

QByteArray readAll(const QString &path) {
    QFile f(path);
    if (!f.open(QIODevice::ReadOnly))
        return {};
    return f.readAll();
}

// Monotonic clock shared by the samplers (rates need wall time).
qint64 monotonicMs() {
    static QElapsedTimer timer;
    if (!timer.isValid())
        timer.start();
    return timer.elapsed();
}

bool parseCpuFields(const QList<QByteArray> &fields, CpuTimes *out) {
    // "cpuN user nice system idle iowait irq softirq steal ..." — at least
    // the first four are present on any kernel we care about.
    if (fields.size() < 5)
        return false;
    auto at = [&](int i) -> qulonglong {
        return i < fields.size() ? fields.at(i).toULongLong() : 0;
    };
    out->user = at(1);
    out->nice = at(2);
    out->system = at(3);
    out->idle = at(4);
    out->iowait = at(5);
    out->irq = at(6);
    out->softirq = at(7);
    out->steal = at(8);
    return true;
}

double percent(qulonglong part, qulonglong whole) {
    return whole ? 100.0 * double(part) / double(whole) : 0.0;
}

} // namespace

bool parseProcStat(const QByteArray &text, CpuTimes *total, QVector<CpuTimes> *perCore) {
    bool haveTotal = false;
    for (const QByteArray &line : text.split('\n')) {
        if (!line.startsWith("cpu"))
            continue;
        const QList<QByteArray> fields = line.simplified().split(' ');
        CpuTimes t;
        if (!parseCpuFields(fields, &t))
            continue;
        if (fields.at(0) == "cpu") {
            *total = t;
            haveTotal = true;
        } else if (perCore) {
            perCore->append(t);
        }
    }
    return haveTotal;
}

MemInfo parseMemInfo(const QByteArray &text) {
    MemInfo mem;
    for (const QByteArray &line : text.split('\n')) {
        const int colon = line.indexOf(':');
        if (colon < 0)
            continue;
        const QByteArray key = line.left(colon);
        const qulonglong kb = line.mid(colon + 1).simplified().split(' ').value(0).toULongLong();
        if (key == "MemTotal")
            mem.totalKb = kb;
        else if (key == "MemAvailable")
            mem.availableKb = kb;
        else if (key == "SwapTotal")
            mem.swapTotalKb = kb;
        else if (key == "SwapFree")
            mem.swapFreeKb = kb;
    }
    return mem;
}

NetTotals parseNetDev(const QByteArray &text) {
    NetTotals net;
    for (const QByteArray &line : text.split('\n')) {
        const int colon = line.indexOf(':');
        if (colon < 0)
            continue; // the two header lines
        const QByteArray iface = line.left(colon).simplified();
        if (iface == "lo")
            continue;
        const QList<QByteArray> fields = line.mid(colon + 1).simplified().split(' ');
        // rx: bytes packets errs drop fifo frame compressed multicast | tx: bytes ...
        if (fields.size() < 9)
            continue;
        net.rxBytes += fields.at(0).toULongLong();
        net.txBytes += fields.at(8).toULongLong();
    }
    return net;
}

DiskTotals parseDiskStats(const QByteArray &text) {
    // Whole-disk device names only; a partition row (sda1, nvme0n1p2) would
    // double-count I/O already reported by its parent disk.
    static const QRegularExpression wholeDisk(
        QStringLiteral("^(sd[a-z]+|nvme\\d+n\\d+|vd[a-z]+|mmcblk\\d+)$"));
    DiskTotals disk;
    for (const QByteArray &line : text.split('\n')) {
        const QList<QByteArray> fields = line.simplified().split(' ');
        // major minor name reads-completed reads-merged sectors-read ms-reading
        // writes-completed writes-merged sectors-written ...
        if (fields.size() < 10)
            continue;
        const QString name = QString::fromLatin1(fields.at(2));
        if (!wholeDisk.match(name).hasMatch())
            continue;
        disk.readSectors += fields.at(5).toULongLong();
        disk.writeSectors += fields.at(9).toULongLong();
    }
    return disk;
}

bool parsePidStat(const QByteArray &text, qulonglong pageSize, ProcessSample *out) {
    // "pid (comm) state ppid ... utime(14) stime(15) ... rss(24)". comm may
    // contain spaces AND parentheses, so anchor on the last ')'.
    const int open = text.indexOf('(');
    const int close = text.lastIndexOf(')');
    if (open < 0 || close < open)
        return false;
    out->pid = text.left(open).trimmed().toInt();
    out->name = QString::fromUtf8(text.mid(open + 1, close - open - 1));
    const QList<QByteArray> rest = text.mid(close + 1).simplified().split(' ');
    // rest[0]=state(3) rest[1]=ppid(4) ... rest[11]=utime(14) rest[12]=stime(15)
    // ... rest[21]=rss(24)
    if (rest.size() < 22)
        return false;
    out->state = rest.at(0).isEmpty() ? '?' : rest.at(0).at(0);
    out->ppid = rest.at(1).toInt();
    out->utime = rest.at(11).toULongLong();
    out->stime = rest.at(12).toULongLong();
    out->nice = rest.at(16).toInt();
    out->threads = rest.at(17).toInt();
    out->rssBytes = rest.at(21).toULongLong() * pageSize;
    return out->pid > 0;
}

QString stateName(char state) {
    switch (state) {
    case 'R': return QStringLiteral("Running");
    case 'S': return QStringLiteral("Sleeping");
    case 'D': return QStringLiteral("Disk sleep");
    case 'Z': return QStringLiteral("Zombie");
    case 'T': return QStringLiteral("Stopped");
    case 't': return QStringLiteral("Traced");
    case 'I': return QStringLiteral("Idle");
    case 'X': return QStringLiteral("Dead");
    }
    return QString(QChar::fromLatin1(state));
}

QVector<UserRollup> rollupByUser(const QVector<ProcessSample> &samples) {
    QHash<QString, UserRollup> byUser;
    for (const ProcessSample &p : samples) {
        UserRollup &u = byUser[p.user];
        u.user = p.user;
        u.processes += 1;
        u.cpuPercent += p.cpuPercent;
        u.rssBytes += p.rssBytes;
    }
    QVector<UserRollup> out;
    out.reserve(byUser.size());
    for (const UserRollup &u : byUser)
        out.append(u);
    std::sort(out.begin(), out.end(),
              [](const UserRollup &a, const UserRollup &b) { return a.user < b.user; });
    return out;
}

QVector<ProcessSample> ProcessSampler::sample() {
    const qulonglong pageSize = qulonglong(sysconf(_SC_PAGESIZE));

    CpuTimes machine;
    parseProcStat(readAll(QStringLiteral("/proc/stat")), &machine, nullptr);
    const qulonglong machineTotal = machine.total();
    const qulonglong totalDelta = machineTotal > prevTotal_ ? machineTotal - prevTotal_ : 0;

    QVector<ProcessSample> out;
    QHash<int, qulonglong> ticksNow;
    const QDir proc(QStringLiteral("/proc"));
    const QStringList entries =
        proc.entryList(QDir::Dirs | QDir::NoDotAndDotDot, QDir::Name);
    out.reserve(entries.size());
    for (const QString &entry : entries) {
        bool numeric = false;
        const int pid = entry.toInt(&numeric);
        if (!numeric || pid <= 0)
            continue;
        const QString base = QStringLiteral("/proc/") + entry;

        ProcessSample p;
        if (!parsePidStat(readAll(base + QStringLiteral("/stat")), pageSize, &p))
            continue; // raced with exit

        p.cmdline = QString::fromUtf8(readAll(base + QStringLiteral("/cmdline")))
                        .replace(QChar(u'\0'), QChar(u' '))
                        .trimmed();

        struct stat st{};
        if (::stat((base).toLocal8Bit().constData(), &st) == 0) {
            auto it = userCache_.constFind(st.st_uid);
            if (it == userCache_.constEnd()) {
                const struct passwd *pw = ::getpwuid(st.st_uid);
                it = userCache_.insert(st.st_uid,
                                       pw ? QString::fromLocal8Bit(pw->pw_name)
                                          : QString::number(st.st_uid));
            }
            p.user = it.value();
        }

        const qulonglong ticks = p.utime + p.stime;
        ticksNow.insert(p.pid, ticks);
        const auto prev = prevTicks_.constFind(p.pid);
        if (prev != prevTicks_.constEnd() && totalDelta > 0 && ticks >= prev.value())
            p.cpuPercent = percent(ticks - prev.value(), totalDelta);
        out.append(p);
    }

    prevTicks_ = ticksNow;
    prevTotal_ = machineTotal;
    return out;
}

SystemSampler::Snapshot SystemSampler::sample() {
    Snapshot snap;

    CpuTimes total;
    QVector<CpuTimes> cores;
    parseProcStat(readAll(QStringLiteral("/proc/stat")), &total, &cores);
    snap.mem = parseMemInfo(readAll(QStringLiteral("/proc/meminfo")));
    const NetTotals net = parseNetDev(readAll(QStringLiteral("/proc/net/dev")));
    const DiskTotals disk = parseDiskStats(readAll(QStringLiteral("/proc/diskstats")));
    const qint64 nowMs = monotonicMs();

    if (primed_) {
        const qulonglong totalDelta = total.total() - prevTotal_.total();
        snap.cpuPercent = percent(total.active() - prevTotal_.active(), totalDelta);
        const int n = qMin(cores.size(), prevCores_.size());
        snap.perCorePercent.reserve(n);
        for (int i = 0; i < n; ++i) {
            const qulonglong coreDelta = cores.at(i).total() - prevCores_.at(i).total();
            snap.perCorePercent.append(
                percent(cores.at(i).active() - prevCores_.at(i).active(), coreDelta));
        }
        const double seconds = double(nowMs - prevMonotonicMs_) / 1000.0;
        if (seconds > 0) {
            snap.rxBytesPerSec = double(net.rxBytes - prevNet_.rxBytes) / seconds;
            snap.txBytesPerSec = double(net.txBytes - prevNet_.txBytes) / seconds;
            snap.readBytesPerSec = double(disk.readSectors - prevDisk_.readSectors) * 512.0 / seconds;
            snap.writeBytesPerSec = double(disk.writeSectors - prevDisk_.writeSectors) * 512.0 / seconds;
        }
    }

    prevTotal_ = total;
    prevCores_ = cores;
    prevNet_ = net;
    prevDisk_ = disk;
    prevMonotonicMs_ = nowMs;
    primed_ = true;
    return snap;
}

} // namespace ezra
