#pragma once

#include <PolkitQt1/Agent/Listener>
#include <PolkitQt1/Agent/Session>
#include <PolkitQt1/Details>
#include <PolkitQt1/Identity>

class AuthDialog;

// HeDE's PolicyKit authentication agent — the native replacement for
// lxqt-policykit-agent. Registers as the session's agent; when polkitd needs
// authorisation for a privileged action (GeST's package manager, system config,
// bootloader/kernel, …) it drives a Helm-themed password dialog and hands the
// response back over the polkit session. Modelled on lxqt-policykit + the
// polkit-qt example.
class HelmPolkitAgent : public PolkitQt1::Agent::Listener {
    Q_OBJECT
public:
    explicit HelmPolkitAgent(QObject *parent = nullptr);

    // Register this listener for the current login session.
    bool registerAgent();

    void initiateAuthentication(const QString &actionId,
                                const QString &message,
                                const QString &iconName,
                                const PolkitQt1::Details &details,
                                const QString &cookie,
                                const PolkitQt1::Identity::List &identities,
                                PolkitQt1::Agent::AsyncResult *result) override;
    bool initiateAuthenticationFinish() override;
    void cancelAuthentication() override;

private slots:
    void onDialogAccepted();
    void onDialogRejected();
    void onSessionRequest(const QString &request, bool echo);
    void onSessionCompleted(bool gainedAuthorization);
    void onSessionShowError(const QString &text);
    void onSessionShowInfo(const QString &text);

private:
    void startSession();
    void finish();

    AuthDialog *m_dialog = nullptr;
    PolkitQt1::Agent::Session *m_session = nullptr;
    PolkitQt1::Agent::AsyncResult *m_result = nullptr;
    PolkitQt1::Identity::List m_identities;
    QString m_cookie;
};
