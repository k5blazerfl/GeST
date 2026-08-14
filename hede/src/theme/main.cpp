#include "theme.h"

#include <QCoreApplication>

#include <cstdio>

// helm-theme: apply a HeDE appearance choice to GTK + the shell palette.
//   helm-theme --dark --accent=#33d6c8 [--gtk-theme=Adwaita-dark] [--icon-theme=Papirus]
int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    const helm::ThemeSpec spec = helm::parseThemeArgs(app.arguments().mid(1));
    const QStringList written = helm::applyTheme(spec);
    if (written.isEmpty()) {
        std::fprintf(stderr, "helm-theme: failed to write any config\n");
        return 1;
    }
    for (const QString &p : written)
        std::printf("wrote %s\n", qPrintable(p));
    return 0;
}
