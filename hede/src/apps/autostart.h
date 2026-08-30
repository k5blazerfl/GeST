// XDG autostart (autostart-spec): scanning shared by helm-autostart (the
// session runner) and EzRA's Startup tab, plus the enable/disable toggle.
// A user file shadows a system file of the same id; Hidden=true disables;
// OnlyShowIn/NotShowIn gate by desktop. Toggling never touches system
// files — disabling writes a user override, enabling removes it (or the
// Hidden key from a real user entry).
#pragma once

#include "desktopentry.h"

namespace helm {

struct AutostartEntry {
    DesktopEntry entry;
    QString file;        // the path that defines it (user shadows system)
    bool system = false; // true if it came from a system dir
    bool enabled = true; // !Hidden (ShowIn-excluded entries are not listed)
};

// User autostart dir first ($XDG_CONFIG_HOME/autostart), then the system
// dirs ($XDG_CONFIG_DIRS/autostart, default /etc/xdg/autostart).
QStringList defaultAutostartDirs();

// Scan dirs (first = user, wins by id) for entries whose ShowIn rules admit
// `desktop`; name-sorted. Disabled (Hidden) entries are included so a
// Startup tab can re-enable them — a runner starts only the enabled ones.
QVector<AutostartEntry> scanAutostart(const QStringList &dirs, const QString &desktop);

// Enable/disable by user override in `userDir`. Disabling a system entry
// writes a minimal shadowing file with Hidden=true; disabling a user entry
// sets Hidden=true in place. Enabling removes the Hidden key, and removes
// the file entirely if it was only a shadowing stub.
bool setAutostartEnabled(const AutostartEntry &entry, bool enabled, const QString &userDir);

} // namespace helm
