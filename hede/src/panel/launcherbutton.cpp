#include "launcherbutton.h"

#include <QProcess>

namespace helm {

LauncherButton::LauncherButton(const QString &text, const QString &command, QWidget *parent)
    : QPushButton(text, parent), m_command(command) {
    connect(this, &QPushButton::clicked, this, [this] {
        const QStringList parts = QProcess::splitCommand(m_command);
        if (parts.isEmpty())
            return;
        QProcess::startDetached(parts.first(), parts.mid(1));
    });
}

} // namespace helm
