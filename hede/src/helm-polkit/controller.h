#pragma once

#include <QObject>

#include "authdialog.h"

extern "C" {
#include <gio/gio.h>
#include <polkitagent/polkitagent.h>
}

// Drives one authentication request at a time: shows the Helm dialog and runs the
// PAM conversation through a PolkitAgentSession (polkit's own C library — no
// polkit-qt binding). The GObject listener (agentlistener.cpp) hands requests
// here; Qt's glib-backed event loop lets the session's GObject signals fire
// inline, so no separate GLib main loop is needed.
class AgentController : public QObject {
    Q_OBJECT
public:
    explicit AgentController(QObject *parent = nullptr);

    // Entry point from the listener vfunc; takes ownership of the GTask.
    void begin(const QString &message, const QString &iconName,
               const QList<AuthIdentity> &identities, const QString &cookie,
               GTask *task, GCancellable *cancellable);

    // Forwarded from the PolkitAgentSession / GCancellable C callbacks.
    void sessionRequest();
    void sessionCompleted(bool gained);
    void sessionShowError(const QString &text);
    void sessionShowInfo(const QString &text);
    void cancelled();

private Q_SLOTS:
    void onDialogAccepted();
    void onDialogRejected();

private:
    void startSession();
    void clearSession(bool cancel);
    void finish(bool result);

    AuthDialog *m_dialog = nullptr;
    PolkitAgentSession *m_session = nullptr;
    GTask *m_task = nullptr;
    GCancellable *m_cancellable = nullptr;
    gulong m_cancelId = 0;
    QList<AuthIdentity> m_identities;
    QString m_cookie;
};
