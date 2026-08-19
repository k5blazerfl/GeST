#pragma once

#include <QSet>
#include <QString>

// SeFE file operations. The naming helpers are pure (unit-tested); the copy/move
// helpers touch the filesystem (integration-tested with a temp dir). The window
// drives these from the keyboard contract + context menus (docs/design/sefe.md).
namespace helm::sefe {

// A non-colliding "New folder" name for a directory whose entries are `existing`:
// "New folder", then "New folder (2)", "New folder (3)", …
QString newFolderName(const QSet<QString> &existing);

// A Windows-style copy name for `name` given the `existing` entries: inserts
// " - Copy" before the extension ("Report.txt" → "Report - Copy.txt", "Work" →
// "Work - Copy"), then " - Copy (2)", " - Copy (3)", … on further collisions.
QString copyName(const QString &name, const QSet<QString> &existing);

// Recursively copy `src` (file, dir, or symlink target) to the full path `dst`,
// creating parents. `dst` must not already exist (callers disambiguate first).
bool copyRecursively(const QString &src, const QString &dst);

// Move `src` to the full path `dst`: a rename when possible, else a recursive
// copy followed by removing `src` (handles a cross-filesystem move).
bool moveItem(const QString &src, const QString &dst);

} // namespace helm::sefe
