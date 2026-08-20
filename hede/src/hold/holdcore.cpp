#include "holdcore.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>

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

// Stream the current entry's data into `target`.
Result writeData(struct archive *a, const QString &target) {
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
    }
    if (rc != ARCHIVE_EOF) {
        r.error = QStringLiteral("read error in %1").arg(QFileInfo(target).fileName());
        return r;
    }
    r.ok = true;
    return r;
}

// Extract all entries, or just the one named `only` (nullptr = all).
Result extractImpl(const QString &archive, const QString &destDir, const QString *only) {
    Result r;
    Reader reader;
    if (!reader.open(archive)) {
        r.error = reader.error();
        return r;
    }
    const QString base = QDir::cleanPath(destDir);
    QDir().mkpath(base);

    struct archive_entry *entry = nullptr;
    bool found = false;
    while (archive_read_next_header(reader.a, &entry) == ARCHIVE_OK) {
        const QString name = QString::fromUtf8(archive_entry_pathname(entry));
        if (only && name != *only) {
            archive_read_data_skip(reader.a);
            continue;
        }
        found = true;
        const QString target = safeJoin(base, name);
        if (target.isEmpty()) { // Zip-Slip: skip an escaping path
            archive_read_data_skip(reader.a);
            if (only)
                break;
            continue;
        }
        if (entryIsDir(entry, name)) {
            QDir().mkpath(target);
        } else {
            const Result w = writeData(reader.a, target);
            if (!w.ok)
                return w;
        }
        if (only)
            break;
    }
    if (only && !found) {
        r.error = QStringLiteral("no such entry: %1").arg(*only);
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

Result extractAll(const QString &archive, const QString &destDir) {
    return extractImpl(archive, destDir, nullptr);
}

Result extract(const QString &archive, const QString &entryPath, const QString &destDir) {
    return extractImpl(archive, destDir, &entryPath);
}

Result create(const QStringList &files, const QString &archivePath) {
    Result r;
    struct archive *a = archive_write_new();
    configureWriteFormat(a, archivePath.toLower());
    if (archive_write_open_filename(a, archivePath.toLocal8Bit().constData()) != ARCHIVE_OK) {
        r.error = QString::fromUtf8(archive_error_string(a));
        archive_write_free(a);
        return r;
    }
    for (const QString &f : files) {
        const Result ar = addPath(a, f, QFileInfo(f).fileName());
        if (!ar.ok) {
            archive_write_close(a);
            archive_write_free(a);
            return ar;
        }
    }
    archive_write_close(a);
    archive_write_free(a);
    r.ok = true;
    return r;
}

} // namespace helm::hold
