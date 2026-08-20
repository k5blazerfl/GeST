#include "ops.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>

namespace helm::sefe {

namespace {

// Split a name into stem + extension (".txt"), at the last dot — but not a
// leading dot (dotfiles have no extension). ext is empty or starts with '.'.
void splitStemExt(const QString &name, QString &stem, QString &ext) {
    const int dot = name.lastIndexOf(QLatin1Char('.'));
    if (dot > 0) {
        stem = name.left(dot);
        ext = name.mid(dot);
    } else {
        stem = name;
        ext.clear();
    }
}

} // namespace

QString newFolderName(const QSet<QString> &existing) {
    const QString base = QStringLiteral("New folder");
    if (!existing.contains(base))
        return base;
    for (int n = 2;; ++n) {
        const QString c = base + QStringLiteral(" (%1)").arg(n);
        if (!existing.contains(c))
            return c;
    }
}

QString copyName(const QString &name, const QSet<QString> &existing) {
    QString stem, ext;
    splitStemExt(name, stem, ext);
    QString cand = stem + QStringLiteral(" - Copy") + ext;
    if (!existing.contains(cand))
        return cand;
    for (int n = 2;; ++n) {
        cand = stem + QStringLiteral(" - Copy (%1)").arg(n) + ext;
        if (!existing.contains(cand))
            return cand;
    }
}

bool copyRecursively(const QString &src, const QString &dst) {
    const QFileInfo si(src);
    if (si.isDir()) {
        if (!QDir().mkpath(dst))
            return false;
        const QDir sd(src);
        const QFlags<QDir::Filter> filter =
            QDir::NoDotAndDotDot | QDir::AllEntries | QDir::Hidden | QDir::System;
        for (const QString &entry : sd.entryList(filter)) {
            if (!copyRecursively(sd.filePath(entry), QDir(dst).filePath(entry)))
                return false;
        }
        return true;
    }
    if (!QDir().mkpath(QFileInfo(dst).absolutePath()))
        return false;
    return QFile::copy(src, dst);
}

bool moveItem(const QString &src, const QString &dst) {
    if (QFile::rename(src, dst))
        return true; // same filesystem — atomic
    // Cross-filesystem: copy then remove the source.
    if (!copyRecursively(src, dst))
        return false;
    return QFileInfo(src).isDir() ? QDir(src).removeRecursively() : QFile::remove(src);
}

} // namespace helm::sefe
