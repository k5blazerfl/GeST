#pragma once

#include <QDialog>
#include <QList>
#include <QString>

class QComboBox;
class QLabel;
class QLineEdit;
class QPushButton;

// One admin identity the user may authenticate as.
struct AuthIdentity {
    int uid = -1;
    QString name;
};

// The Helm-themed authentication prompt: the action's message, which admin
// identity to authenticate as (when there's a choice), a password field, and a
// status line for polkit's error/info messages. No polkit binding — plain data.
class AuthDialog : public QDialog {
    Q_OBJECT
public:
    AuthDialog(const QString &message, const QString &iconName,
               const QList<AuthIdentity> &identities, QWidget *parent = nullptr);

    QString password() const;
    int selectedUid() const;

    void setError(const QString &text);
    void setInfo(const QString &text);
    void clearPassword();
    void setBusy(bool busy);      // lock fields while polkit checks

private:
    QList<AuthIdentity> m_identities;
    QComboBox *m_identityCombo = nullptr;
    QLineEdit *m_password = nullptr;
    QLabel *m_status = nullptr;
    QPushButton *m_ok = nullptr;
};
