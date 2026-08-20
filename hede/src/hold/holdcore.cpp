#include "holdcore.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QSet>
#include <QStringDecoder>

#include <filesystem>
#include <system_error>

#include <archive.h>
#include <archive_entry.h>

namespace helm::hold {

// --- pure helpers ---

bool isArchive(const QString &path) {
    static const QStringList suffixes = {
        QStringLiteral(".tar.gz"),  QStringLiteral(".tar.bz2"), QStringLiteral(".tar.xz"),
        QStringLiteral(".zip"),     QStringLiteral(".tar"),     QStringLiteral(".tgz"),
        QStringLiteral(".tbz2"),    QStringLiteral(".txz"),     QStringLiteral(".7z"),
        QStringLiteral(".rar"),     QStringLiteral(".cbz"),     QStringLiteral(".cbr"),
    };
    const QString lower = path.toLower();
    for (const QString &s : suffixes) {
        if (lower.endsWith(s))
            return true;
    }
    return false;
}

namespace {
// CP437 high half (0x80..0xFF) → Unicode. The historical IBM-PC / zip code page;
// the low half (0x00..0x7F) is ASCII and passes through unchanged.
const char16_t kCp437High[128] = {
    0x00C7, 0x00FC, 0x00E9, 0x00E2, 0x00E4, 0x00E0, 0x00E5, 0x00E7, 0x00EA, 0x00EB,
    0x00E8, 0x00EF, 0x00EE, 0x00EC, 0x00C4, 0x00C5, 0x00C9, 0x00E6, 0x00C6, 0x00F4,
    0x00F6, 0x00F2, 0x00FB, 0x00F9, 0x00FF, 0x00D6, 0x00DC, 0x00A2, 0x00A3, 0x00A5,
    0x20A7, 0x0192, 0x00E1, 0x00ED, 0x00F3, 0x00FA, 0x00F1, 0x00D1, 0x00AA, 0x00BA,
    0x00BF, 0x2310, 0x00AC, 0x00BD, 0x00BC, 0x00A1, 0x00AB, 0x00BB, 0x2591, 0x2592,
    0x2593, 0x2502, 0x2524, 0x2561, 0x2562, 0x2556, 0x2555, 0x2563, 0x2551, 0x2557,
    0x255D, 0x255C, 0x255B, 0x2510, 0x2514, 0x2534, 0x252C, 0x251C, 0x2500, 0x253C,
    0x255E, 0x255F, 0x255A, 0x2554, 0x2569, 0x2566, 0x2560, 0x2550, 0x256C, 0x2567,
    0x2568, 0x2564, 0x2565, 0x2559, 0x2558, 0x2552, 0x2553, 0x256B, 0x256A, 0x2518,
    0x250C, 0x2588, 0x2584, 0x258C, 0x2590, 0x2580, 0x03B1, 0x00DF, 0x0393, 0x03C0,
    0x03A3, 0x03C3, 0x00B5, 0x03C4, 0x03A6, 0x0398, 0x03A9, 0x03B4, 0x221E, 0x03C6,
    0x03B5, 0x2229, 0x2261, 0x00B1, 0x2265, 0x2264, 0x2320, 0x2321, 0x00F7, 0x2248,
    0x00B0, 0x2219, 0x00B7, 0x221A, 0x207F, 0x00B2, 0x25A0, 0x00A0,
};
} // namespace

QString decodeEntryName(const QByteArray &rawName) {
    QStringDecoder utf8(QStringConverter::Utf8);
    const QString asUtf8 = utf8.decode(rawName);
    if (!utf8.hasError())
        return asUtf8;
    // Not valid UTF-8 — fall back to CP437 so the name stays legible.
    QString out;
    out.reserve(rawName.size());
    for (unsigned char c : rawName)
        out += (c < 0x80) ? QChar(c) : QChar(kCp437High[c - 0x80]);
    return out;
}

QString safeJoin(const QString &destDir, const QString &entryPath) {
    const QString base = QDir::cleanPath(destDir);
    const QString joined = QDir::cleanPath(base + QLatin1Char('/') + entryPath);
    if (joined == base || joined.startsWith(base + QLatin1Char('/')))
        return joined;
    return QString(); // escapes the destination — reject
}

bool symlinkEscapes(const QString &destDir, const QString &entryPath,
                    const QString &linkTarget) {
    if (linkTarget.isEmpty())
        return false; // nothing to point at — nothing to escape
    if (QDir::isAbsolutePath(linkTarget))
        return true; // an absolute target always leaves the sandbox
    const QString base = QDir::cleanPath(destDir);
    // The link lives at base/entryPath; a relative target resolves against its dir.
    const QString linkDir =
        QDir::cleanPath(base + QLatin1Char('/') + entryPath + QLatin1String("/.."));
    const QString resolved = QDir::cleanPath(linkDir + QLatin1Char('/') + linkTarget);
    return !(resolved == base || resolved.startsWith(base + QLatin1Char('/')));
}

// --- libarchive plumbing ---

namespace {

// RAII for a read handle.
struct Reader {
    struct archive *a = archive_read_new();
    ~Reader() { archive_read_free(a); }
    bool open(const QString &path) {
        archive_read_support_filter_all(a);
        archive_read_support_format_all(a);
        return archive_read_open_filename(a, path.toLocal8Bit().constData(), 10240) == ARCHIVE_OK;
    }
    QString error() const { return QString::fromUtf8(archive_error_string(a)); }
};

bool entryIsDir(struct archive_entry *e, const QString &name) {
    return archive_entry_filetype(e) == AE_IFDIR || name.endsWith(QLatin1Char('/'));
}

// Stream the current entry's data into `target`, accumulating the running
// `written` total and refusing mid-stream if it blows past the size cap (so a
// single giant entry is caught before it fills the disk, not after).
Result writeData(struct archive *a, const QString &target, qint64 &written,
                 const Limits &limits) {
    Result r;
    QDir().mkpath(QFileInfo(target).absolutePath());
    QFile f(target);
    if (!f.open(QIODevice::WriteOnly)) {
        r.error = QStringLiteral("cannot write %1").arg(target);
        return r;
    }
    const void *buff = nullptr;
    size_t len = 0;
    la_int64_t offset = 0;
    int rc;
    while ((rc = archive_read_data_block(a, &buff, &len, &offset)) == ARCHIVE_OK) {
        if (f.write(static_cast<const char *>(buff), static_cast<qint64>(len)) < 0) {
            r.error = QStringLiteral("short write to %1").arg(target);
            return r;
        }
        written += static_cast<qint64>(len);
        if (limits.maxTotalBytes > 0 && written > limits.maxTotalBytes) {
            r.error = QStringLiteral("archive exceeds the %1-byte extraction limit")
                          .arg(limits.maxTotalBytes);
            return r;
        }
    }
    if (rc != ARCHIVE_EOF) {
        r.error = QStringLiteral("read error in %1").arg(QFileInfo(target).fileName());
        return r;
    }
    r.ok = true;
    return r;
}

// Create a symlink at `target` pointing to `linkTarget` (caller has already checked
// the target stays inside the destination via symlinkEscapes). Replaces an existing
// node at `target` — a full overwrite policy lands in A1d.
Result writeSymlink(const QString &linkTarget, const QString &target) {
    Result r;
    QDir().mkpath(QFileInfo(target).absolutePath());
    const std::filesystem::path at(target.toLocal8Bit().toStdString());
    std::error_code ec;
    std::filesystem::remove(at, ec);
    ec.clear();
    std::filesystem::create_symlink(
        std::filesystem::path(linkTarget.toLocal8Bit().toStdString()), at, ec);
    if (ec) {
        r.error = QStringLiteral("cannot create symlink %1").arg(target);
        return r;
    }
    r.ok = true;
    return r;
}

// A free "name (1).ext" beside `path`, for the keep-both overwrite policy.
QString uniqueName(const QString &path) {
    const QFileInfo fi(path);
    const QString dir = fi.absolutePath();
    const QString base = fi.completeBaseName();
    const QString suffix = fi.suffix();
    for (int i = 1; i < 10000; ++i) {
        const QString cand = suffix.isEmpty()
            ? QStringLiteral("%1/%2 (%3)").arg(dir, fi.fileName(), QString::number(i))
            : QStringLiteral("%1/%2 (%3).%4").arg(dir, base, QString::number(i), suffix);
        if (!QFileInfo::exists(cand) && !QFileInfo(cand).isSymLink())
            return cand;
    }
    return path; // give up (astronomically unlikely) and let Replace win
}

// Resolve the on-disk target for `target` under the overwrite `policy`. Returns the
// path to write, or "" to skip this entry (no collision → `target` unchanged).
QString resolveOverwrite(const QString &target, Overwrite policy) {
    const QFileInfo fi(target);
    if (!fi.exists() && !fi.isSymLink())
        return target; // nothing there — no conflict
    switch (policy) {
    case Overwrite::Skip:
        return QString();
    case Overwrite::KeepBoth:
        return uniqueName(target);
    case Overwrite::Replace:
        break;
    }
    return target;
}

Result cancelledResult() {
    Result r;
    r.error = QStringLiteral("cancelled");
    return r; // ok stays false
}

// Extract entries from `archive` into `destDir`. `want` selects which: null =
// every entry; otherwise an entry is taken if its name is in `want` or lies under
// a requested directory. `progress` reports count-based advances and can cancel.
Result extractImpl(const QString &archive, const QString &destDir, const QSet<QString> *want,
                   qint64 total, const Progress &progress, const Limits &limits,
                   Overwrite overwrite) {
    Result r;
    Reader reader;
    if (!reader.open(archive)) {
        r.error = reader.error();
        return r;
    }
    const QString base = QDir::cleanPath(destDir);
    QDir().mkpath(base);

    QSet<QString> remaining = want ? *want : QSet<QString>();
    qint64 done = 0;
    qint64 written = 0; // running uncompressed bytes, for the zip-bomb caps
    int seen = 0;       // headers seen, for the entry-count cap
    struct archive_entry *entry = nullptr;
    while (archive_read_next_header(reader.a, &entry) == ARCHIVE_OK) {
        if (progress.cancelled && progress.cancelled())
            return cancelledResult();
        if (limits.maxEntries > 0 && ++seen > limits.maxEntries) {
            r.error = QStringLiteral("archive exceeds the %1-entry limit").arg(limits.maxEntries);
            return r;
        }
        const QString name = decodeEntryName(archive_entry_pathname(entry));
        if (want) {
            bool wanted = remaining.remove(name);
            if (!wanted) // the entry IS a requested directory (maybe "dir/") or lies under one
                for (const QString &w : *want)
                    if (name == w || name == w + QLatin1Char('/') ||
                        name.startsWith(w + QLatin1Char('/'))) {
                        wanted = true;
                        remaining.remove(w); // the request is satisfied by its dir/descendants
                        break;
                    }
            if (!wanted) {
                archive_read_data_skip(reader.a);
                continue;
            }
        }
        const QString target = safeJoin(base, name);
        if (target.isEmpty()) { // Zip-Slip: the entry's own path escapes the destination
            archive_read_data_skip(reader.a);
            r.skipped << name;
            continue;
        }
        if (archive_entry_filetype(entry) == AE_IFLNK) {
            const QString linkTarget = QString::fromUtf8(archive_entry_symlink(entry));
            if (symlinkEscapes(base, name, linkTarget)) { // symlink-escape: refuse it
                archive_read_data_skip(reader.a);
                r.skipped << name;
                continue;
            }
            const QString dest = resolveOverwrite(target, overwrite);
            if (dest.isEmpty()) { // Skip policy, existing target
                archive_read_data_skip(reader.a);
                continue;
            }
            const Result w = writeSymlink(linkTarget, dest);
            if (!w.ok)
                return w;
        } else if (entryIsDir(entry, name)) {
            QDir().mkpath(target); // dirs merge; overwrite policy is a file concern
        } else {
            const QString dest = resolveOverwrite(target, overwrite);
            if (dest.isEmpty()) { // Skip policy, existing target
                archive_read_data_skip(reader.a);
                continue;
            }
            const Result w = writeData(reader.a, dest, written, limits);
            if (!w.ok)
                return w;
        }
        // Ratio guard (the compressed-vs-uncompressed zip bomb), checked only past a
        // floor so ordinary small files never trip it.
        if (limits.maxRatio > 0 && written > limits.ratioFloorBytes) {
            const la_int64_t consumed = archive_filter_bytes(reader.a, -1);
            if (consumed > 0 && written / static_cast<qint64>(consumed) > limits.maxRatio) {
                r.error = QStringLiteral("archive expands beyond the %1:1 ratio limit")
                              .arg(limits.maxRatio);
                return r;
            }
        }
        if (progress.step)
            progress.step(++done, total, name);
    }
    if (want && !remaining.isEmpty()) {
        r.error = QStringLiteral("no such entry: %1").arg(*remaining.constBegin());
        return r;
    }
    r.ok = true;
    return r;
}

// Pick the write format/filter for an output path's extension.
void configureWriteFormat(struct archive *a, const QString &lower) {
    if (lower.endsWith(QLatin1String(".zip")) || lower.endsWith(QLatin1String(".cbz"))) {
        archive_write_set_format_zip(a);
        return;
    }
    if (lower.endsWith(QLatin1String(".7z"))) {
        archive_write_set_format_7zip(a);
        return;
    }
    archive_write_set_format_pax_restricted(a); // a portable tar
    if (lower.endsWith(QLatin1String(".gz")) || lower.endsWith(QLatin1String(".tgz")))
        archive_write_add_filter_gzip(a);
    else if (lower.endsWith(QLatin1String(".bz2")) || lower.endsWith(QLatin1String(".tbz2")))
        archive_write_add_filter_bzip2(a);
    else if (lower.endsWith(QLatin1String(".xz")) || lower.endsWith(QLatin1String(".txz")))
        archive_write_add_filter_xz(a);
}

// Add one host path (file or dir) to the write handle under `archiveName`.
Result addPath(struct archive *a, const QString &fsPath, const QString &archiveName) {
    Result r;
    const QFileInfo info(fsPath);

    if (info.isDir()) {
        struct archive_entry *e = archive_entry_new();
        archive_entry_set_pathname(e, (archiveName + QLatin1Char('/')).toLocal8Bit().constData());
        archive_entry_set_filetype(e, AE_IFDIR);
        archive_entry_set_perm(e, 0755);
        const int rc = archive_write_header(a, e);
        archive_entry_free(e);
        if (rc != ARCHIVE_OK) {
            r.error = QString::fromUtf8(archive_error_string(a));
            return r;
        }
        const QDir dir(fsPath);
        for (const QString &child :
             dir.entryList(QDir::NoDotAndDotDot | QDir::AllEntries | QDir::Hidden | QDir::System)) {
            const Result cr = addPath(a, dir.filePath(child), archiveName + QLatin1Char('/') + child);
            if (!cr.ok)
                return cr;
        }
        r.ok = true;
        return r;
    }

    QFile f(fsPath);
    if (!f.open(QIODevice::ReadOnly)) {
        r.error = QStringLiteral("cannot read %1").arg(fsPath);
        return r;
    }
    const QByteArray bytes = f.readAll();
    struct archive_entry *e = archive_entry_new();
    archive_entry_set_pathname(e, archiveName.toLocal8Bit().constData());
    archive_entry_set_size(e, bytes.size());
    archive_entry_set_filetype(e, AE_IFREG);
    archive_entry_set_perm(e, 0644);
    if (info.lastModified().isValid())
        archive_entry_set_mtime(e, info.lastModified().toSecsSinceEpoch(), 0);
    int rc = archive_write_header(a, e);
    archive_entry_free(e);
    if (rc != ARCHIVE_OK) {
        r.error = QString::fromUtf8(archive_error_string(a));
        return r;
    }
    if (!bytes.isEmpty() && archive_write_data(a, bytes.constData(), bytes.size()) < 0) {
        r.error = QString::fromUtf8(archive_error_string(a));
        return r;
    }
    r.ok = true;
    return r;
}

} // namespace

Listing list(const QString &archive) {
    Listing out;
    Reader reader;
    if (!reader.open(archive)) {
        out.error = reader.error();
        return out;
    }
    struct archive_entry *entry = nullptr;
    int rc;
    while ((rc = archive_read_next_header(reader.a, &entry)) == ARCHIVE_OK) {
        const QString name = decodeEntryName(archive_entry_pathname(entry));
        Entry e;
        e.path = name;
        e.size = archive_entry_size(entry);
        e.isDir = entryIsDir(entry, name);
        if (archive_entry_filetype(entry) == AE_IFLNK) {
            e.type = EntryType::Symlink;
            e.linkTarget = QString::fromUtf8(archive_entry_symlink(entry));
        } else {
            e.type = e.isDir ? EntryType::Directory : EntryType::File;
        }
        if (archive_entry_mtime_is_set(entry))
            e.mtime = QDateTime::fromSecsSinceEpoch(archive_entry_mtime(entry));
        out.entries.append(e);
        archive_read_data_skip(reader.a);
    }
    if (rc != ARCHIVE_EOF) {
        out.error = reader.error();
        return out;
    }
    out.ok = true;
    return out;
}

Result extractAll(const QString &archive, const QString &destDir, const Progress &progress,
                  const Limits &limits, Overwrite overwrite) {
    return extractImpl(archive, destDir, nullptr, -1, progress, limits, overwrite);
}

Result extract(const QString &archive, const QString &entryPath, const QString &destDir) {
    const QSet<QString> want{entryPath};
    return extractImpl(archive, destDir, &want, 1, {}, {}, Overwrite::Replace);
}

Result extractEntries(const QString &archive, const QStringList &entryPaths, const QString &destDir,
                      const Progress &progress, const Limits &limits, Overwrite overwrite) {
    if (entryPaths.isEmpty()) {
        Result r;
        r.ok = true;
        return r;
    }
    const QSet<QString> want(entryPaths.begin(), entryPaths.end());
    return extractImpl(archive, destDir, &want, entryPaths.size(), progress, limits, overwrite);
}

Result create(const QStringList &files, const QString &archivePath, const Progress &progress) {
    Result r;
    struct archive *a = archive_write_new();
    configureWriteFormat(a, archivePath.toLower());
    if (archive_write_open_filename(a, archivePath.toLocal8Bit().constData()) != ARCHIVE_OK) {
        r.error = QString::fromUtf8(archive_error_string(a));
        archive_write_free(a);
        return r;
    }
    qint64 done = 0;
    for (const QString &f : files) {
        if (progress.cancelled && progress.cancelled()) {
            archive_write_close(a);
            archive_write_free(a);
            QFile::remove(archivePath); // don't leave a half-written archive
            return cancelledResult();
        }
        const Result ar = addPath(a, f, QFileInfo(f).fileName());
        if (!ar.ok) {
            archive_write_close(a);
            archive_write_free(a);
            QFile::remove(archivePath);
            return ar;
        }
        if (progress.step)
            progress.step(++done, files.size(), QFileInfo(f).fileName());
    }
    archive_write_close(a);
    archive_write_free(a);
    r.ok = true;
    return r;
}

} // namespace helm::hold
