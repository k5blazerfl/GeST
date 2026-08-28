#include "agent.h"

#include "authdialog.h"

#include <PolkitQt1/Subject>

#include <unistd.h>

using namespace PolkitQt1;

HelmPolkitAgent::HelmPolkitAgent(QObject *parent) : Agent::Listener(parent) {}

bool HelmPolkitAgent::registerAgent() {
    // Register for the session that contains this process.
    UnixSessionSubject session(static_cast<qint64>(::getpid()));
    return registerListener(session,
                            QStringLiteral("/org/hede/PolicyKit1/AuthenticationAgent"));
}

void HelmPolkitAgent::initiateAuthentication(
    const QString &actionId, const QString &message, const QString &iconName,
    const Details &details, const QString &cookie,
    const Identity::List &identities, Agent::AsyncResult *result) {
    Q_UNUSED(details);

    // A previous request should have finished; if not, cancel it defensively.
    if (m_result)
        cancelAuthentication();

    m_result = result;
    m_cookie = cookie;
    m_identities = identities;

    m_dialog = new AuthDialog(actionId, message, iconName, identities);
    connect(m_dialog, &QDialog::accepted, this, &HelmPolkitAgent::onDialogAccepted);
    connect(m_dialog, &QDialog::rejected, this, &HelmPolkitAgent::onDialogRejected);
    m_dialog->show();
    m_dialog->raise();
    m_dialog->activateWindow();
}

void HelmPolkitAgent::startSession() {
    if (m_session) {
        m_session->disconnect(this);
        m_session->deleteLater();
    }
    m_session = new Agent::Session(m_dialog->selectedIdentity(), m_cookie, m_result);
    connect(m_session, &Agent::Session::request, this, &HelmPolkitAgent::onSessionRequest);
    connect(m_session, &Agent::Session::completed, this, &HelmPolkitAgent::onSessionCompleted);
    connect(m_session, &Agent::Session::showError, this, &HelmPolkitAgent::onSessionShowError);
    connect(m_session, &Agent::Session::showInfo, this, &HelmPolkitAgent::onSessionShowInfo);
    m_session->initiate();
}

void HelmPolkitAgent::onDialogAccepted() {
    if (!m_dialog)
        return;
    m_dialog->setBusy(true);      // lock the fields while we check
    startSession();
}

void HelmPolkitAgent::onSessionRequest(const QString &request, bool echo) {
    Q_UNUSED(request);
    Q_UNUSED(echo);
    if (m_session && m_dialog)     // PAM is asking for the secret; hand it the password
        m_session->setResponse(m_dialog->password());
}

void HelmPolkitAgent::onSessionCompleted(bool gainedAuthorization) {
    if (gainedAuthorization) {
        if (m_result)
            m_result->setCompleted();
        finish();
        return;
    }
    // Wrong secret — let the user try again on the same dialog.
    if (m_session) {
        m_session->disconnect(this);
        m_session->deleteLater();
        m_session = nullptr;
    }
    if (m_dialog) {
        m_dialog->setError(tr("Authentication failed — try again."));
        m_dialog->clearPassword();
        m_dialog->setBusy(false);
    }
}

void HelmPolkitAgent::onSessionShowError(const QString &text) {
    if (m_dialog)
        m_dialog->setError(text);
}

void HelmPolkitAgent::onSessionShowInfo(const QString &text) {
    if (m_dialog)
        m_dialog->setInfo(text);
}

void HelmPolkitAgent::onDialogRejected() {
    if (m_session)
        m_session->cancel();
    if (m_result) {
        m_result->setError(tr("Authentication cancelled."));
        m_result->setCompleted();
    }
    finish();
}

bool HelmPolkitAgent::initiateAuthenticationFinish() {
    return true;
}

void HelmPolkitAgent::cancelAuthentication() {
    if (m_session)
        m_session->cancel();
    finish();                      // polkitd is cancelling; don't complete the result
}

void HelmPolkitAgent::finish() {
    if (m_session) {
        m_session->disconnect(this);
        m_session->deleteLater();
        m_session = nullptr;
    }
    if (m_dialog) {
        m_dialog->disconnect(this);
        m_dialog->deleteLater();
        m_dialog = nullptr;
    }
    m_result = nullptr;
    m_identities.clear();
    m_cookie.clear();
}
