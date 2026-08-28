#pragma once

#include <QDialog>

#include <PolkitQt1/Identity>

class QComboBox;
class QLabel;
class QLineEdit;
class QPushButton;

// The Helm-themed authentication prompt: the action's message, which admin
// identity to authenticate as (when there's a choice), a password field, and a
// status line for polkit's error/info messages.
class AuthDialog : public QDialog {
    Q_OBJECT
public:
    AuthDialog(const QString &actionId, const QString &message,
               const QString &iconName, const PolkitQt1::Identity::List &identities,
               QWidget *parent = nullptr);

    QString password() const;
    PolkitQt1::Identity selectedIdentity() const;

    void setError(const QString &text);
    void setInfo(const QString &text);
    void clearPassword();
    void setBusy(bool busy);      // lock fields while polkit checks

private:
    PolkitQt1::Identity::List m_identities;
    QComboBox *m_identityCombo = nullptr;
    QLineEdit *m_password = nullptr;
    QLabel *m_status = nullptr;
    QPushButton *m_ok = nullptr;
};
