#pragma once

#include <QString>
#include <QStringList>
#include <QVector>

namespace helm {

// A jump-list action from a .desktop file ([Desktop Action <id>]).
struct DesktopAction {
    QString id;
    QString name;
    QString exec;
};

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
    QStringList mimeTypes;          // MimeType= entries this app declares it opens
    QStringList categories;         // Categories= (freedesktop groups → menu sections)
    QStringList onlyShowIn;         // OnlyShowIn= (autostart/menu desktop gating)
    QStringList notShowIn;          // NotShowIn=
    QVector<DesktopAction> actions; // jump-list actions, in Actions= order

    // The ShowIn verdict for a desktop name (e.g. "HeDE"): OnlyShowIn wins,
    // then NotShowIn excludes; both empty → shown everywhere.
    bool shownIn(const QString &desktop) const {
        if (!onlyShowIn.isEmpty())
            return onlyShowIn.contains(desktop);
        return !notShowIn.contains(desktop);
    }
};

// Parse a .desktop file's text: the [Desktop Entry] group plus any
// [Desktop Action <id>] groups referenced by Actions=. Locale-suffixed keys
// (e.g. Name[fr]) are ignored in favour of the unlocalised key.
DesktopEntry parseDesktopEntry(const QString &text, const QString &id = QString());

// The XDG application directories, highest priority first.
QStringList defaultApplicationDirs();

// Scan the given dirs for launchable Type=Application entries, name-sorted.
QVector<DesktopEntry> scanDesktopEntries(const QStringList &dirs);

// Case-insensitive filter over name/comment/exec, name-sorted. Empty query → all.
QVector<DesktopEntry> filterEntries(const QVector<DesktopEntry> &entries, const QString &query);

// The entries that declare they handle `mimeType` (exact MimeType= match),
// preserving the input order. For a file manager's "Open with" recommendations.
QVector<DesktopEntry> handlersForMimeType(const QVector<DesktopEntry> &entries,
                                          const QString &mimeType);

// Expand an Exec into an argv: strip field codes (%f %u %U %i …), %% → %, split.
QStringList commandArgv(const QString &exec);
QStringList commandArgv(const DesktopEntry &entry); // entry.exec

} // namespace helm
