#include "sensors.h"

#include <QDir>
#include <QElapsedTimer>
#include <QFile>

namespace ezra {

namespace {

QByteArray readAll(const QString &path) {
    QFile f(path);
    if (!f.open(QIODevice::ReadOnly))
        return {};
    return f.readAll().trimmed();
}

qint64 monotonicMs() {
    static QElapsedTimer timer;
    if (!timer.isValid())
        timer.start();
    return timer.elapsed();
}

QVector<TempReading> readHwmonTemps() {
    QVector<TempReading> out;
    const QDir hwmon(QStringLiteral("/sys/class/hwmon"));
    const QStringList chips = hwmon.entryList({QStringLiteral("hwmon*")}, QDir::Dirs);
    for (const QString &chip : chips) {
        const QString base = hwmon.absoluteFilePath(chip);
        const QString name = QString::fromLatin1(readAll(base + QStringLiteral("/name")));
        const QStringList inputs =
            QDir(base).entryList({QStringLiteral("temp*_input")}, QDir::Files);
        for (const QString &input : inputs) {
            bool ok = false;
            const double milli = readAll(base + QLatin1Char('/') + input).toDouble(&ok);
            if (!ok)
                continue;
            const QString labelFile =
                base + QLatin1Char('/') + QString(input).replace(QStringLiteral("_input"),
                                                                 QStringLiteral("_label"));
            QString label = QString::fromLatin1(readAll(labelFile));
            if (label.isEmpty())
                label = input.section(QLatin1Char('_'), 0, 0);
            out.append({name, label, milli / 1000.0});
        }
    }
    return out;
}

// Top-level RAPL package zones only ("intel-rapl:0", not the ":0:0"
// subzones — those are already contained in their package's counter).
qulonglong readRaplEnergyUj(bool *found) {
    qulonglong total = 0;
    *found = false;
    const QDir powercap(QStringLiteral("/sys/class/powercap"));
    const QStringList zones =
        powercap.entryList({QStringLiteral("intel-rapl:*")}, QDir::Dirs);
    for (const QString &zone : zones) {
        if (zone.count(QLatin1Char(':')) != 1)
            continue;
        bool ok = false;
        const qulonglong uj =
            readAll(powercap.absoluteFilePath(zone) + QStringLiteral("/energy_uj"))
                .toULongLong(&ok);
        if (ok) {
            total += uj;
            *found = true;
        }
    }
    return total;
}

// First hwmon chip with a power sensor (µW), e.g. amdgpu's PPT on APUs —
// user-readable where RAPL's energy_uj is root-only since the side-channel
// mitigations. Instantaneous, so no delta math needed.
bool readHwmonPowerWatts(double *watts, QString *source) {
    const QDir hwmon(QStringLiteral("/sys/class/hwmon"));
    const QStringList chips = hwmon.entryList({QStringLiteral("hwmon*")}, QDir::Dirs);
    for (const QString &chip : chips) {
        const QString base = hwmon.absoluteFilePath(chip);
        for (const char *file : {"/power1_average", "/power1_input"}) {
            bool ok = false;
            const double uw = readAll(base + QLatin1String(file)).toDouble(&ok);
            if (!ok || uw <= 0)
                continue;
            *watts = uw / 1e6;
            *source = QString::fromLatin1(readAll(base + QStringLiteral("/name")));
            return true;
        }
    }
    return false;
}

// Battery draw in watts while discharging; 0 otherwise.
double readBatteryWatts() {
    const QDir supplies(QStringLiteral("/sys/class/power_supply"));
    const QStringList batteries = supplies.entryList({QStringLiteral("BAT*")}, QDir::Dirs);
    for (const QString &bat : batteries) {
        const QString base = supplies.absoluteFilePath(bat);
        if (readAll(base + QStringLiteral("/status")) != "Discharging")
            continue;
        bool ok = false;
        const double uw = readAll(base + QStringLiteral("/power_now")).toDouble(&ok);
        if (ok && uw > 0)
            return uw / 1e6;
        const double ua = readAll(base + QStringLiteral("/current_now")).toDouble(&ok);
        if (!ok)
            continue;
        bool okV = false;
        const double uv = readAll(base + QStringLiteral("/voltage_now")).toDouble(&okV);
        if (okV)
            return ua * uv / 1e12;
    }
    return 0.0;
}

} // namespace

bool hottestOf(const QVector<TempReading> &readings, TempReading *out) {
    if (readings.isEmpty())
        return false;
    *out = readings.first();
    for (const TempReading &r : readings)
        if (r.degC > out->degC)
            *out = r;
    return true;
}

double wattsFromEnergyDelta(qulonglong prevUj, qulonglong nowUj, qint64 elapsedMs) {
    if (nowUj <= prevUj || elapsedMs <= 0)
        return 0.0; // counter wrapped (or first sample) — skip this window
    return double(nowUj - prevUj) / 1e6 / (double(elapsedMs) / 1000.0);
}

SensorSampler::Snapshot SensorSampler::sample() {
    Snapshot snap;

    snap.hasTemp = hottestOf(readHwmonTemps(), &snap.hottest);

    bool raplFound = false;
    const qulonglong energyUj = readRaplEnergyUj(&raplFound);
    const qint64 nowMs = monotonicMs();
    if (raplFound) {
        snap.hasPower = true;
        snap.powerSource = QStringLiteral("pkg");
        if (primed_)
            snap.packageWatts = wattsFromEnergyDelta(prevEnergyUj_, energyUj,
                                                     nowMs - prevMonotonicMs_);
        prevEnergyUj_ = energyUj;
        prevMonotonicMs_ = nowMs;
        primed_ = true;
    } else {
        snap.hasPower = readHwmonPowerWatts(&snap.packageWatts, &snap.powerSource);
    }
    if (snap.hasPower)
        snap.batteryWatts = readBatteryWatts();

    const QDir drm(QStringLiteral("/sys/class/drm"));
    const QStringList cards = drm.entryList({QStringLiteral("card?")}, QDir::Dirs);
    for (const QString &card : cards) {
        const QString device = drm.absoluteFilePath(card) + QStringLiteral("/device");
        bool ok = false;
        const double busy =
            readAll(device + QStringLiteral("/gpu_busy_percent")).toDouble(&ok);
        if (!ok)
            continue; // no busy% (NVIDIA proprietary, old kernels)
        snap.hasGpu = true;
        snap.gpuBusyPercent = busy;
        snap.vramUsedBytes =
            readAll(device + QStringLiteral("/mem_info_vram_used")).toULongLong();
        snap.vramTotalBytes =
            readAll(device + QStringLiteral("/mem_info_vram_total")).toULongLong();
        break;
    }

    return snap;
}

} // namespace ezra
