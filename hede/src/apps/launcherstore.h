#pragma once

#include <QByteArray>
#include <QHash>
#include <QString>
#include <QStringList>

namespace helm {

// Per-app launch history: how often and how recently it was started.
struct AppUsage {
    int count = 0;
    qint64 lastUsed = 0; // seconds since epoch
};

// The launcher's persistent state: pinned apps (ordered) + usage history, so the
// Start menu can show Pinned and Recent (most-recently/-frequently-used).
struct LauncherStore {
    QStringList pinned;              // desktop-file ids, in pin order
    QHash<QString, AppUsage> usage;  // id -> usage
};

// --- pure (unit-tested) ---
LauncherStore parseStore(const QByteArray &json);
QByteArray serializeStore(const LauncherStore &s);

// The top-n ids by frequency (then recency), skipping anything in `exclude`
// (e.g. the pinned ids, so Recent doesn't repeat them).
QStringList recentIds(const LauncherStore &s, int n, const QStringList &exclude = {});

// Record a launch: bump count and set lastUsed. Pure — caller persists.
void recordLaunch(LauncherStore &s, const QString &id, qint64 nowEpoch);

// Add the id if absent, remove it if present. Pure.
void togglePin(LauncherStore &s, const QString &id);

// --- side-effecting ---
QString launcherStorePath();      // $XDG_DATA_HOME/hede/launcher.json
LauncherStore loadStore();        // parse the file (empty store on error)
bool saveStore(const LauncherStore &s);

// Default pins for a fresh profile, filtered to the ids that actually exist.
QStringList defaultPins(const QStringList &available);

} // namespace helm
