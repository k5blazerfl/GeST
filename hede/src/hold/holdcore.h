#pragma once

#include <QDateTime>
#include <QList>
#include <QMetaType>
#include <QString>
#include <QStringList>

#include <functional>

// hold-core — HeDE's archive engine (libarchive), shared by Seahorse (in-place
// browsing + quick extract/compress) and Hold-the-app (docs/design/hold.md).
// This header is the whole public surface; the pure helpers (isArchive,
// safeJoin) are unit-tested without touching libarchive.
namespace helm::hold {

// What kind of node an entry is. (Regular files, directories, and symlinks; other
// libarchive types — devices/fifos — are surfaced as File and not extracted.)
enum class EntryType { File, Directory, Symlink };

// One member of an archive.
struct Entry {
    QString path;    // path within the archive, '/'-separated (e.g. "sub/a.txt")
    qint64 size = 0; // uncompressed size in bytes (0 for directories)
    bool isDir = false;                    // == (type == EntryType::Directory)
    EntryType type = EntryType::File;
    QString linkTarget;                    // symlink target (empty unless type == Symlink)
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
    // Entries the safety pass refused (Zip-Slip name escape, or an unsafe symlink
    // whose target leaves the destination). Extraction of the rest still succeeds
    // (`ok == true`); the UI can report "N entries skipped for safety".
    QStringList skipped;
};

// A progress/cancel hook for the long-running ops (A0, docs/design/archive-support.md).
// `step(done, total, name)` is called as the op advances — `total` is -1 when it
// isn't known ahead of time (streaming extract), so a UI should show an
// indeterminate bar then. If `cancelled()` returns true the op stops early and
// returns Result{ok=false, error="cancelled"}. Both members may be empty (no
// reporting / never cancels) — the ops null-check before calling. Passed by the
// caller directly, or built by helm::hold::Job to marshal onto its signals.
struct Progress {
    std::function<void(qint64 done, qint64 total, const QString &name)> step;
    std::function<bool()> cancelled;
};

// Extraction safety limits — the zip-bomb defense (A1, decision D). A run that
// would exceed any cap is refused with Result{ok=false} (partial output may remain;
// the op failed). Set a field to 0 (or negative) to disable that cap.
struct Limits {
    qint64 maxTotalBytes = 8LL * 1024 * 1024 * 1024; // 8 GiB uncompressed, total
    int maxEntries = 200000;                         // entry-count cap
    int maxRatio = 1000;                             // uncompressed:compressed ceiling
    qint64 ratioFloorBytes = 32LL * 1024 * 1024;     // ...only checked past this output
};

// How extraction resolves a destination file that already exists (A1, decision D).
// Seahorse pre-scans for collisions, prompts once, and passes the chosen policy in;
// Replace (overwrite) is the default and matches the prior behavior. KeepBoth writes
// the incoming entry under a disambiguated "name (1).ext".
enum class Overwrite { Replace, Skip, KeepBoth };

// --- pure helpers (no libarchive; unit-tested) ---

// True if `path` looks like a browsable archive by extension (zip/tar family,
// 7z, rar, cbz/cbr). What Seahorse's openIndex tests to decide "walk into it".
bool isArchive(const QString &path);

// True if hold-core can REBUILD this format (rewrite/create) — the whole isArchive
// set except what libarchive reads but can't write (RAR/CBR). Seahorse gates
// in-archive editing on this: a rar browses read-only, a zip is mutable.
bool isWritableArchive(const QString &path);

// Decode an archive entry's raw name bytes to a QString: UTF-8 when the bytes are
// valid UTF-8, otherwise CP437 (the historical zip code page) so legacy DOS/zip
// names stay readable instead of collapsing to U+FFFD replacement characters.
QString decodeEntryName(const QByteArray &rawName);

// Resolve an archive entry to an absolute path under `destDir`, or "" if it
// would escape it — the Zip-Slip guard. `destDir` is treated as the boundary;
// absolute or "../"-laden entry paths are re-rooted or rejected.
QString safeJoin(const QString &destDir, const QString &entryPath);

// True if a symlink placed at `entryPath` (an archive-relative path under
// `destDir`) pointing to `linkTarget` would resolve OUTSIDE `destDir`. An absolute
// target always escapes; a relative one is resolved against the symlink's own
// directory. Escaping symlinks are refused at extract time (the symlink-escape
// guard, complementing safeJoin which only guards the entry's own name).
bool symlinkEscapes(const QString &destDir, const QString &entryPath,
                    const QString &linkTarget);

// A set of mutations to apply to an archive via rewrite(). All paths are
// archive-relative ('/'-separated). `remove` drops an entry — for a directory, its
// whole subtree. `rename` moves from→to — for a directory, its subtree moves with
// it (prefix rename). `add` ingests a host file/dir/symlink (recursively, like
// create) at `innerPath`. Removes win over renames when both name a path.
struct Edits {
    struct Add {
        QString fsPath;    // host path to ingest
        QString innerPath; // where it lands inside the archive
    };
    struct Rename {
        QString from;
        QString to;
    };
    QList<Add> add;
    QStringList remove;
    QList<Rename> rename;

    bool isEmpty() const { return add.isEmpty() && remove.isEmpty() && rename.isEmpty(); }
};

// --- libarchive-backed engine ---

// List an archive's entries (directories and files).
Listing list(const QString &archive);

// Apply `edits` to `archive` in place (decision A — the streaming mutation engine):
// stream every source entry through a fresh writer of the SAME format + filters
// (dropping removes, applying renames), append the adds, then atomically swap the
// rebuilt archive over the original. The source is never corrupted on failure or
// cancel — the temp is discarded and the original left intact. One pass,
// format-preserving. Formats libarchive can read but not write (e.g. RAR) are
// refused. Delete / rename / new-folder / add in Seahorse all reduce to this.
Result rewrite(const QString &archive, const Edits &edits, const Progress &progress = {});

// Extract every entry into `destDir` (created if needed). Entries whose paths
// would escape `destDir` (safeJoin) or whose symlink target escapes it
// (symlinkEscapes) are skipped and listed in `Result::skipped`; an archive that
// blows past `limits` (a zip bomb) is refused. Reports count-based progress with
// total=-1 (the entry count isn't known until the stream ends).
Result extractAll(const QString &archive, const QString &destDir,
                  const Progress &progress = {}, const Limits &limits = {},
                  Overwrite overwrite = Overwrite::Replace);

// Extract the single entry `entryPath` (its parent dirs recreated) into
// `destDir`. Errors if no such entry. (Single + fast — no progress hook.)
Result extract(const QString &archive, const QString &entryPath, const QString &destDir);

// Extract the named `entryPaths` (and everything under a requested directory) into
// `destDir` in ONE pass over the archive — the multi-select extract. Progress is
// reported against entryPaths.size().
Result extractEntries(const QString &archive, const QStringList &entryPaths,
                      const QString &destDir, const Progress &progress = {},
                      const Limits &limits = {}, Overwrite overwrite = Overwrite::Replace);

// Create an archive at `archivePath` from host `files`, each stored by its base
// name (directories added recursively). Format is inferred from the extension:
// .zip/.cbz → zip, .7z → 7z, else a tar with an optional gzip/bzip2/xz filter
// (.tar, .tar.gz/.tgz, .tar.bz2/.tbz2, .tar.xz/.txz). Reports progress against the
// top-level `files` count; a cancel removes the partial output.
Result create(const QStringList &files, const QString &archivePath, const Progress &progress = {});

} // namespace helm::hold

// Result rides hold::Job::finished across threads — make it a queued-safe metatype.
Q_DECLARE_METATYPE(helm::hold::Result)
