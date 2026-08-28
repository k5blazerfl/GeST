#include "agentlistener.h"
#include "controller.h"

#include "palette.h"     // helm-appearance: applyAppearance / watchAppearance

#include <QApplication>

extern "C" {
#include <polkit/polkit.h>
#include <polkitagent/polkitagent.h>
}

#include <unistd.h>

// helm-polkit — HeDE's PolicyKit authentication agent. Binding-free: it uses
// polkit's own libpolkit-agent-1 / libpolkit-gobject-1 (no polkit-qt), with a
// Helm-themed Qt dialog. Runs headless for the session (labwc autostart);
// replaces lxqt-policykit-agent.
int main(int argc, char **argv) {
    QApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("helm-polkit"));
    app.setApplicationDisplayName(QStringLiteral("HeDE Authentication"));
    app.setDesktopFileName(QStringLiteral("helm-polkit"));
    app.setQuitOnLastWindowClosed(false);   // the agent outlives its dialogs

    helm::applyAppearance();
    helm::watchAppearance();

    AgentController controller;
    PolkitAgentListener *listener = helm_agent_listener_new(&controller);

    GError *error = nullptr;
    PolkitSubject *subject =
        polkit_unix_session_new_for_process_sync(static_cast<gint>(::getpid()), nullptr, &error);
    if (subject == nullptr) {
        qWarning("helm-polkit: cannot resolve this session: %s",
                 error ? error->message : "unknown error");
        return 1;
    }

    gpointer registration = polkit_agent_listener_register(
        listener, POLKIT_AGENT_REGISTER_FLAGS_NONE, subject,
        "/org/hede/PolicyKit1/AuthenticationAgent", nullptr, &error);
    g_object_unref(subject);
    if (registration == nullptr) {
        qWarning("helm-polkit: could not register the agent: %s",
                 error ? error->message : "another agent may already own this session");
        return 1;
    }

    const int rc = app.exec();

    polkit_agent_listener_unregister(registration);
    g_object_unref(listener);
    return rc;
}
