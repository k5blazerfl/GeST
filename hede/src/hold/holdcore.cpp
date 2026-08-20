#include "holdcore.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QSet>

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

Result cancelledResult() {
    Result r;
    r.error = QStringLiteral("cancelled");
    return r; // ok stays false
}

// Extract entries from `archive` into `destDir`. `want` selects which: null =
// every entry; otherwise an entry is taken if its name is in `want` or lies under
// a requested directory. `progress` reports count-based advances and can cancel.
Result extractImpl(const QString &archive, const QString &destDir, const QSet<QString> *want,
                   qint64 total, const Progress &progress, const Limits &limits) {
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
        const QString name = QString::fromUtf8(archive_entry_pathname(entry));
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
            const Result w = writeSymlink(linkTarget, target);
            if (!w.ok)
                return w;
        } else if (entryIsDir(entry, name)) {
            QDir().mkpath(target);
        } else {
            const Result w = writeData(reader.a, target, written, limits);
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
        const QString name = QString::fromUtf8(archive_entry_pathname(entry));
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
                  const Limits &limits) {
    return extractImpl(archive, destDir, nullptr, -1, progress, limits);
}

Result extract(const QString &archive, const QString &entryPath, const QString &destDir) {
    const QSet<QString> want{entryPath};
    return extractImpl(archive, destDir, &want, 1, {}, {});
}

Result extractEntries(const QString &archive, const QStringList &entryPaths, const QString &destDir,
                      const Progress &progress, const Limits &limits) {
    if (entryPaths.isEmpty()) {
        Result r;
        r.ok = true;
        return r;
    }
    const QSet<QString> want(entryPaths.begin(), entryPaths.end());
    return extractImpl(archive, destDir, &want, entryPaths.size(), progress, limits);
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
