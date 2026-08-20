#pragma once

#include <QDateTime>
#include <QList>
#include <QString>
#include <QStringList>

// hold-core — HeDE's archive engine (libarchive), shared by Seahorse (in-place
// browsing + quick extract/compress) and Hold-the-app (docs/design/hold.md).
// This header is the whole public surface; the pure helpers (isArchive,
// safeJoin) are unit-tested without touching libarchive.
namespace helm::hold {

// One member of an archive.
struct Entry {
    QString path;    // path within the archive, '/'-separated (e.g. "sub/a.txt")
    qint64 size = 0; // uncompressed size in bytes (0 for directories)
    bool isDir = false;
    QDateTime mtime; // invalid if the archive records none
};

// The result of listing an archive.
struct Listing {
    bool ok = false;
    QString error;
    QList<Entry> entries;
};

// The result of a mutating op (extract/create).
struct Result {
    bool ok = false;
    QString error;
};

// --- pure helpers (no libarchive; unit-tested) ---

// True if `path` looks like a browsable archive by extension (zip/tar family,
// 7z, rar, cbz/cbr). What Seahorse's openIndex tests to decide "walk into it".
bool isArchive(const QString &path);

// Resolve an archive entry to an absolute path under `destDir`, or "" if it
// would escape it — the Zip-Slip guard. `destDir` is treated as the boundary;
// absolute or "../"-laden entry paths are re-rooted or rejected.
QString safeJoin(const QString &destDir, const QString &entryPath);

// --- libarchive-backed engine ---

// List an archive's entries (directories and files).
Listing list(const QString &archive);

// Extract every entry into `destDir` (created if needed). Entries whose paths
// would escape `destDir` are skipped (safeJoin).
Result extractAll(const QString &archive, const QString &destDir);

// Extract the single entry `entryPath` (its parent dirs recreated) into
// `destDir`. Errors if no such entry.
Result extract(const QString &archive, const QString &entryPath, const QString &destDir);

// Create an archive at `archivePath` from host `files`, each stored by its base
// name (directories added recursively). Format is inferred from the extension:
// .zip/.cbz → zip, .7z → 7z, else a tar with an optional gzip/bzip2/xz filter
// (.tar, .tar.gz/.tgz, .tar.bz2/.tbz2, .tar.xz/.txz).
Result create(const QStringList &files, const QString &archivePath);

} // namespace helm::hold
