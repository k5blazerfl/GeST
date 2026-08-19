#pragma once

#include <QString>

// SeFE — the Seahorse File Explorer. HeDE's native file manager (see
// docs/design/sefe.md). This header holds the pure, unit-tested helpers; the
// window/Qt glue lives in window.{h,cpp} and the entry point in main.cpp.
namespace helm::sefe {

// The location SeFE opens at — the user's home ($HOME, else QDir::homePath()).
QString initialDir();

// The window title for a directory: "<name> — Seahorse", where <name> is
// "Home" for the home dir, the folder's base name otherwise, and the path
// itself for the filesystem root ("/").
QString windowTitle(const QString &dir);

} // namespace helm::sefe
