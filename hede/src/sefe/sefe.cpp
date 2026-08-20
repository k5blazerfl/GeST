#include "sefe.h"

#include "holdcore.h"

#include <QDir>
#include <QFileInfo>
#include <QStandardPaths>

namespace helm::sefe {

QString initialDir() {
    return qEnvironmentVariable("HOME", QDir::homePath());
}

QString windowTitle(const QString &dir) {
    QString name;
    if (dir == initialDir()) {
        name = QStringLiteral("Home");
    } else {
        name = QDir(dir).dirName(); // base name; empty for the root "/"
        if (name.isEmpty())
            name = dir;
    }
    return name + QStringLiteral(" — Seahorse");
}

QList<Crumb> breadcrumbs(const QString &dir) {
    const QString home = initialDir();
    const QString path = QDir::cleanPath(dir);
    QList<Crumb> out;

    QString acc; // the path accumulated so far, for each trailing segment
    QString rest; // the part still to split into segments
    if (path == home || path.startsWith(home + QLatin1Char('/'))) {
        out.push_back({QStringLiteral("Home"), home});
        acc = home;
        rest = path.mid(home.length());
    } else {
        out.push_back({QStringLiteral("/"), QStringLiteral("/")});
        acc.clear();
        rest = path;
    }

    for (const QString &seg : rest.split(QLatin1Char('/'), Qt::SkipEmptyParts)) {
        acc += QLatin1Char('/') + seg;
        out.push_back({seg, acc});
    }
    return out;
}

QList<Place> places() {
    QList<Place> out;
    out.push_back({QStringLiteral("Home"), initialDir(), QStringLiteral("user-home")});

    const struct {
        QStandardPaths::StandardLocation loc;
        const char *name;
        const char *icon;
    } xdg[] = {
        {QStandardPaths::DesktopLocation, "Desktop", "user-desktop"},
        {QStandardPaths::DocumentsLocation, "Documents", "folder-documents"},
        {QStandardPaths::DownloadLocation, "Downloads", "folder-download"},
        {QStandardPaths::PicturesLocation, "Pictures", "folder-pictures"},
        {QStandardPaths::MusicLocation, "Music", "folder-music"},
        {QStandardPaths::MoviesLocation, "Videos", "folder-videos"},
    };
    for (const auto &e : xdg) {
        const QString p = QStandardPaths::writableLocation(e.loc);
        // Skip the ones QStandardPaths falls back to home for (unconfigured), and
        // any that don't exist on disk.
        if (!p.isEmpty() && p != initialDir() && QDir(p).exists())
            out.push_back({QString::fromLatin1(e.name), p, QString::fromLatin1(e.icon)});
    }

    out.push_back({QStringLiteral("Computer"), QStringLiteral("/"), QStringLiteral("computer")});
    return out;
}

QString parentDir(const QString &dir) {
    const QString p = QDir::cleanPath(dir);
    const int slash = p.lastIndexOf(QLatin1Char('/'));
    if (slash <= 0)
        return QStringLiteral("/");
    return p.left(slash);
}

QString normalizePath(const QString &input, const QString &base) {
    QString s = input.trimmed();
    const QString home = initialDir();
    if (s.isEmpty())
        return base.isEmpty() ? home : base;
    if (s == QLatin1String("~"))
        s = home;
    else if (s.startsWith(QLatin1String("~/")))
        s = home + s.mid(1);
    if (!s.startsWith(QLatin1Char('/'))) {
        const QString b = base.isEmpty() ? home : base;
        s = b + QLatin1Char('/') + s;
    }
    return QDir::cleanPath(s);
}

bool isWindowsExecutable(const QString &path) {
    static const QStringList exts = {QStringLiteral("exe"), QStringLiteral("msi"),
                                     QStringLiteral("lnk"), QStringLiteral("bat")};
    return exts.contains(QFileInfo(path).suffix().toLower());
}

ArchiveSplit splitArchivePath(const QString &path) {
    const QStringList segs = QDir::cleanPath(path).split(QLatin1Char('/'), Qt::SkipEmptyParts);
    QString acc;
    for (int i = 0; i < segs.size(); ++i) {
        acc += QLatin1Char('/') + segs[i];
        if (helm::hold::isArchive(acc) && QFileInfo(acc).isFile())
            return {acc, segs.mid(i + 1).join(QLatin1Char('/'))};
    }
    return {};
}

} // namespace helm::sefe
