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

} // namespace helm::sefe
