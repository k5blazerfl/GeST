#include "agent.h"

#include "palette.h"     // helm-appearance: applyAppearance / watchAppearance

#include <QApplication>

// helm-polkit — HeDE's PolicyKit authentication agent. Runs headless for the
// session (labwc autostart launches it); pops a Helm-themed prompt when a
// privileged action needs authorisation. Replaces lxqt-policykit-agent.
int main(int argc, char **argv) {
    QApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("helm-polkit"));
    app.setApplicationDisplayName(QStringLiteral("HeDE Authentication"));
    app.setDesktopFileName(QStringLiteral("helm-polkit"));
    app.setQuitOnLastWindowClosed(false);   // the agent outlives its dialogs

    helm::applyAppearance();
    helm::watchAppearance();

    HelmPolkitAgent agent;
    if (!agent.registerAgent()) {
        qWarning("helm-polkit: could not register the authentication agent "
                 "(another agent already owns this session?)");
        return 1;
    }
    return app.exec();
}
