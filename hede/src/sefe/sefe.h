#pragma once

#include <QList>
#include <QString>

// SeFE — the Seahorse File Explorer. HeDE's native file manager (see
// docs/design/sefe.md). This header holds the pure, unit-tested helpers; the
// window/Qt glue lives in window.{h,cpp}, addressbar.{h,cpp}, and main.cpp.
namespace helm::sefe {

// The location SeFE opens at — the user's home ($HOME, else QDir::homePath()).
QString initialDir();

// The window title for a directory: "<name> — Seahorse", where <name> is
// "Home" for the home dir, the folder's base name otherwise, and the path
// itself for the filesystem root ("/").
QString windowTitle(const QString &dir);

// One segment of the address bar: a clickable label and the path it navigates to.
struct Crumb {
    QString label;
    QString path;
};

// The breadcrumb trail for a directory. Home-aware: paths under the home dir
// start from a single "Home" crumb (Home → Documents → …); paths elsewhere
// start from the filesystem root ("/" → etc → …).
QList<Crumb> breadcrumbs(const QString &dir);

// A shortcut in the Places pane: a display name, the path it opens, and a
// freedesktop icon name.
struct Place {
    QString name;
    QString path;
    QString icon;
};

// The standard Places: Home, the XDG user dirs that exist (Desktop, Documents,
// Downloads, Pictures, Music, Videos), and Computer ("/").
QList<Place> places();

// The parent of a directory, or the directory itself at the filesystem root.
QString parentDir(const QString &dir);

// Resolve an address-bar entry to an absolute, cleaned path: expands a leading
// "~", and resolves a relative entry against `base` (or home if `base` empty).
QString normalizePath(const QString &input, const QString &base = QString());

// True if `path` names a Windows executable/installer/shortcut by extension
// (.exe/.msi/.lnk/.bat, case-insensitive) — the files SeFE routes to Drydock
// rather than a native handler.
bool isWindowsExecutable(const QString &path);

// A path split into an archive file + a subpath inside it. `archive` empty means
// `path` is an ordinary filesystem path.
struct ArchiveSplit {
    QString archive; // the archive file's path on disk ("" if none)
    QString inner;   // the subpath inside it ("" = the archive root)
};

// Split `path` at the first component that is an existing archive file, so
// "/home/u/photos.zip/vacation" → {"/home/u/photos.zip", "vacation"}. Returns an
// empty `archive` for a plain filesystem path. This is what tells the window it
// has crossed into an archive (browse-in-place).
ArchiveSplit splitArchivePath(const QString &path);

} // namespace helm::sefe
