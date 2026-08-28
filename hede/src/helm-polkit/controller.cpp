#include "controller.h"

extern "C" {
#include <polkit/polkit.h>
}

// --- C signal trampolines: PolkitAgentSession / GCancellable -> controller ---
namespace {
void onRequest(PolkitAgentSession *, const gchar *, gboolean, gpointer user) {
    static_cast<AgentController *>(user)->sessionRequest();
}
void onCompleted(PolkitAgentSession *, gboolean gained, gpointer user) {
    static_cast<AgentController *>(user)->sessionCompleted(gained);
}
void onShowError(PolkitAgentSession *, const gchar *text, gpointer user) {
    static_cast<AgentController *>(user)->sessionShowError(QString::fromUtf8(text ? text : ""));
}
void onShowInfo(PolkitAgentSession *, const gchar *text, gpointer user) {
    static_cast<AgentController *>(user)->sessionShowInfo(QString::fromUtf8(text ? text : ""));
}
void onCancelled(GCancellable *, gpointer user) {
    static_cast<AgentController *>(user)->cancelled();
}
} // namespace

AgentController::AgentController(QObject *parent) : QObject(parent) {}

void AgentController::begin(const QString &message, const QString &iconName,
                            const QList<AuthIdentity> &identities, const QString &cookie,
                            GTask *task, GCancellable *cancellable) {
    if (m_task)                                     // one request at a time
        finish(false);

    m_task = task;
    m_identities = identities;
    m_cookie = cookie;
    m_cancellable = cancellable ? G_CANCELLABLE(g_object_ref(cancellable)) : nullptr;
    if (m_cancellable)
        m_cancelId = g_cancellable_connect(m_cancellable, G_CALLBACK(onCancelled),
                                           this, nullptr);

    m_dialog = new AuthDialog(message, iconName, identities);
    connect(m_dialog, &QDialog::accepted, this, &AgentController::onDialogAccepted);
    connect(m_dialog, &QDialog::rejected, this, &AgentController::onDialogRejected);
    m_dialog->show();
    m_dialog->raise();
    m_dialog->activateWindow();
}

void AgentController::onDialogAccepted() {
    if (!m_dialog)
        return;
    m_dialog->setBusy(true);
    startSession();
}

void AgentController::startSession() {
    clearSession(false);
    PolkitIdentity *id = polkit_unix_user_new(m_dialog->selectedUid());
    m_session = polkit_agent_session_new(id, m_cookie.toUtf8().constData());
    g_object_unref(id);
    g_signal_connect(m_session, "request", G_CALLBACK(onRequest), this);
    g_signal_connect(m_session, "completed", G_CALLBACK(onCompleted), this);
    g_signal_connect(m_session, "show-error", G_CALLBACK(onShowError), this);
    g_signal_connect(m_session, "show-info", G_CALLBACK(onShowInfo), this);
    polkit_agent_session_initiate(m_session);
}

void AgentController::sessionRequest() {
    if (m_session && m_dialog)                      // PAM wants the secret
        polkit_agent_session_response(m_session, m_dialog->password().toUtf8().constData());
}

void AgentController::sessionCompleted(bool gained) {
    if (gained) {
        finish(true);
        return;
    }
    clearSession(false);                            // wrong secret — retry on the same dialog
    if (m_dialog) {
        m_dialog->setError(tr("Authentication failed — try again."));
        m_dialog->clearPassword();
        m_dialog->setBusy(false);
    }
}

void AgentController::sessionShowError(const QString &text) {
    if (m_dialog)
        m_dialog->setError(text);
}

void AgentController::sessionShowInfo(const QString &text) {
    if (m_dialog)
        m_dialog->setInfo(text);
}

void AgentController::onDialogRejected() {
    finish(false);
}

void AgentController::cancelled() {
    finish(false);
}

void AgentController::clearSession(bool cancel) {
    if (!m_session)
        return;
    if (cancel)
        polkit_agent_session_cancel(m_session);
    g_signal_handlers_disconnect_by_data(m_session, this);
    g_object_unref(m_session);
    m_session = nullptr;
}

void AgentController::finish(bool result) {
    clearSession(!result);                          // a non-success closes the session out
    if (m_dialog) {
        m_dialog->disconnect(this);
        m_dialog->deleteLater();
        m_dialog = nullptr;
    }
    if (m_cancellable) {
        if (m_cancelId) {
            g_cancellable_disconnect(m_cancellable, m_cancelId);
            m_cancelId = 0;
        }
        g_object_unref(m_cancellable);
        m_cancellable = nullptr;
    }
    if (m_task) {
        g_task_return_boolean(m_task, result ? TRUE : FALSE);
        g_object_unref(m_task);
        m_task = nullptr;
    }
    m_identities.clear();
    m_cookie.clear();
}
