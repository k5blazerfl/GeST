#pragma once

#include <QString>
#include <QStringList>
#include <QVector>

namespace helm {

// A parsed freedesktop .desktop application entry (the fields the launcher needs).
struct DesktopEntry {
    QString id;      // desktop-file id (basename without .desktop)
    QString name;    // Name
    QString exec;    // Exec (raw, still contains field codes)
    QString icon;    // Icon (theme name or path)
    QString comment; // Comment
    QString type;    // Type (Application/Link/Directory)
    bool noDisplay = false;
    bool hidden = false;
    bool terminal = false;
};

// Parse the [Desktop Entry] group of a .desktop file's text. Locale-suffixed
// keys (e.g. Name[fr]) are ignored in favour of the unlocalised key.
DesktopEntry parseDesktopEntry(const QString &text, const QString &id = QString());

// The XDG application directories, highest priority first
// ($XDG_DATA_HOME/applications, then each of $XDG_DATA_DIRS/applications).
QStringList defaultApplicationDirs();

// Scan the given dirs for *.desktop, keep launchable Type=Application entries
// (drop NoDisplay/Hidden/empty), dedupe by id (first seen wins), name-sorted.
QVector<DesktopEntry> scanDesktopEntries(const QStringList &dirs);

// Case-insensitive filter over name/comment/exec, name-sorted. Empty query → all.
QVector<DesktopEntry> filterEntries(const QVector<DesktopEntry> &entries, const QString &query);

// Expand Exec into an argv: strip field codes (%f %F %u %U %i %c %k %d …),
// turn %% into %, and split into program + arguments.
QStringList commandArgv(const DesktopEntry &entry);

} // namespace helm
