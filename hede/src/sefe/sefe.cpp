#include "sefe.h"

#include <QDir>

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

} // namespace helm::sefe
