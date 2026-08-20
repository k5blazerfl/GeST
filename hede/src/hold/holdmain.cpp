#include "holdwindow.h"

#include "palette.h" // helm-appearance

#include <QApplication>
#include <QFileDialog>

// Hold — the Seahorse fleet's archive manager (docs/design/hold.md, H4). Opens
// the archive named on the command line (or via a file dialog), themed by the
// active biome like the rest of HeDE.
int main(int argc, char **argv) {
    QApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("hold"));
    app.setApplicationDisplayName(QStringLiteral("Hold"));
    app.setDesktopFileName(QStringLiteral("hold"));
    helm::applyAppearance();
    helm::watchAppearance();

    QString archive = argc > 1 ? QString::fromLocal8Bit(argv[1]) : QString();
    if (archive.isEmpty()) {
        archive = QFileDialog::getOpenFileName(nullptr, QStringLiteral("Open archive"));
        if (archive.isEmpty())
            return 0;
    }

    helm::hold::HoldWindow window(archive);
    window.show();
    return app.exec();
}
