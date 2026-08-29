// Thermals / power / GPU sampling for the Performance tab, all from sysfs:
// temperatures from /sys/class/hwmon, package watts from the RAPL powercap
// (works on AMD too), battery draw from /sys/class/power_supply, GPU busy%
// + VRAM from the amdgpu sysfs. Absence is normal (NVIDIA has no busy%
// file, desktops have no battery) — the has* flags gate the tiles.
#pragma once

#include <QString>
#include <QVector>

namespace ezra {

struct TempReading {
    QString chip;  // hwmon name ("k10temp", "amdgpu")
    QString label; // sensor label ("Tctl", "edge") or the input name
    double degC = 0.0;
};

// Pure: the hottest reading, false if the list is empty.
bool hottestOf(const QVector<TempReading> &readings, TempReading *out);

// Pure: watts from a cumulative µJ counter delta; 0 on wrap/backwards or
// non-positive elapsed time.
double wattsFromEnergyDelta(qulonglong prevUj, qulonglong nowUj, qint64 elapsedMs);

class SensorSampler {
public:
    struct Snapshot {
        bool hasTemp = false;
        TempReading hottest;
        bool hasPower = false;
        double packageWatts = 0.0; // RAPL delta, or an hwmon power sensor
        QString powerSource;       // "pkg" (RAPL) or the hwmon chip name
        double batteryWatts = 0.0; // positive while discharging, else 0
        bool hasGpu = false;
        double gpuBusyPercent = 0.0;
        qulonglong vramUsedBytes = 0, vramTotalBytes = 0;
    };
    Snapshot sample();

private:
    bool primed_ = false;
    qulonglong prevEnergyUj_ = 0;
    qint64 prevMonotonicMs_ = 0;
};

} // namespace ezra
