#include "world.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QStandardPaths>

#include <algorithm>

namespace helm {

QString World::wallpaperPath() const {
    if (wallpaperImage.isEmpty() || baseDir.isEmpty())
        return QString();
    const QString p = QDir(baseDir).filePath(wallpaperImage);
    return QFileInfo::exists(p) ? p : QString();
}

namespace {

// Strip one layer of matching surrounding quotes (values like '#3aa6c4').
QString unquote(QString v) {
    v = v.trimmed();
    if (v.size() >= 2) {
        const QChar q = v.front();
        if ((q == QLatin1Char('\'') || q == QLatin1Char('"')) && v.back() == q)
            return v.mid(1, v.size() - 2);
    }
    return v;
}

int indentOf(const QString &line) {
    int n = 0;
    while (n < line.size() && line.at(n) == QLatin1Char(' '))
        ++n;
    return n;
}

} // namespace

World parseWorldYaml(const QString &text, const QString &baseDir) {
    World w;
    w.baseDir = baseDir;
    QString section; // current top-level mapping key (a line ending in ':')

    const QStringList lines = text.split(QLatin1Char('\n'));
    for (const QString &raw : lines) {
        // Only whole-line comments/blanks are skipped — values may legitimately
        // contain '#' (hex colours), so inline-comment stripping is avoided.
        const QString stripped = raw.trimmed();
        if (stripped.isEmpty() || stripped.startsWith(QLatin1Char('#')))
            continue;

        const int colon = raw.indexOf(QLatin1Char(':'));
        if (colon < 0)
            continue;
        const QString key = raw.left(colon).trimmed();
        const QString val = unquote(raw.mid(colon + 1));

        if (indentOf(raw) == 0) {
            // A bare "key:" opens a mapping; "key: value" is a top scalar.
            section = val.isEmpty() ? key : QString();
            if (key == QLatin1String("id"))
                w.id = val;
            else if (key == QLatin1String("name"))
                w.name = val;
            else if (key == QLatin1String("accent"))
                w.accent = val;
        } else if (section == QLatin1String("wallpaper_art")) {
            if (key == QLatin1String("image"))
                w.wallpaperImage = val;
            else if (key == QLatin1String("fit"))
                w.wallpaperFit = val;
        } else if (section == QLatin1String("bar")) {
            if (key == QLatin1String("style"))
                w.barStyle = val;
            else if (key == QLatin1String("tint"))
                w.barTint = val;
        }
        // decoration_art / credit and any deeper nesting are ignored for now.
    }
    return w;
}

namespace {

// The world search roots, highest priority first: $HELM_WORLDS_DIR (dev/tests),
// then each XDG data dir's `hede/worlds` (the package installs the defaults
// under /usr/share/hede/worlds).
QStringList worldRoots() {
    QStringList roots;
    const QByteArray env = qgetenv("HELM_WORLDS_DIR");
    if (!env.isEmpty())
        roots << QString::fromLocal8Bit(env);
    const auto dataDirs = QStandardPaths::standardLocations(QStandardPaths::GenericDataLocation);
    for (const QString &d : dataDirs)
        roots << d + QStringLiteral("/hede/worlds");
    return roots;
}

// Load the world in directory `dir` (its theme.yaml), or an invalid World.
World loadWorldDir(const QString &dir) {
    QFile f(QDir(dir).filePath(QStringLiteral("theme.yaml")));
    if (!f.open(QIODevice::ReadOnly | QIODevice::Text))
        return World();
    return parseWorldYaml(QString::fromUtf8(f.readAll()), dir);
}

} // namespace

World loadWorld(const QString &id) {
    if (id.isEmpty())
        return World();
    for (const QString &root : worldRoots()) {
        const World w = loadWorldDir(QDir(root).filePath(id));
        if (w.valid())
            return w;
    }
    return World();
}

QList<World> listWorlds() {
    QList<World> out;
    QStringList seen;
    for (const QString &root : worldRoots()) {
        const QDir dir(root);
        const auto entries = dir.entryList(QDir::Dirs | QDir::NoDotAndDotDot, QDir::Name);
        for (const QString &id : entries) {
            if (seen.contains(id))
                continue; // an earlier root already provided this id
            const World w = loadWorldDir(dir.filePath(id));
            if (w.valid()) {
                out << w;
                seen << w.id;
            }
        }
    }
    std::sort(out.begin(), out.end(),
              [](const World &a, const World &b) { return a.name.localeAwareCompare(b.name) < 0; });
    return out;
}

} // namespace helm
