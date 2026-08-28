#include "authdialog.h"

#include <QComboBox>
#include <QDialogButtonBox>
#include <QGridLayout>
#include <QIcon>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QVBoxLayout>

using namespace PolkitQt1;

namespace {
// "unix-user:root" -> "root"; falls back to the raw string.
QString identityName(const Identity &id) {
    const QString s = id.toString();
    const int c = s.lastIndexOf(QLatin1Char(':'));
    return c >= 0 ? s.mid(c + 1) : s;
}
} // namespace

AuthDialog::AuthDialog(const QString &actionId, const QString &message,
                       const QString &iconName, const Identity::List &identities,
                       QWidget *parent)
    : QDialog(parent), m_identities(identities) {
    setWindowTitle(tr("Authentication Required"));
    setModal(true);
    setWindowFlag(Qt::Dialog);

    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(20, 20, 20, 16);
    root->setSpacing(14);

    // Header: icon + title.
    auto *head = new QHBoxLayout;
    auto *icon = new QLabel(this);
    QIcon ico = QIcon::fromTheme(iconName.isEmpty() ? QStringLiteral("dialog-password")
                                                    : iconName);
    icon->setPixmap(ico.pixmap(48, 48));
    auto *title = new QLabel(tr("<b>Authentication Required</b>"), this);
    head->addWidget(icon);
    head->addSpacing(8);
    head->addWidget(title, 1);
    root->addLayout(head);

    // The action's own message (what's being authorised).
    auto *msg = new QLabel(message, this);
    msg->setWordWrap(true);
    root->addWidget(msg);

    // Identity + password grid.
    auto *grid = new QGridLayout;
    grid->setColumnStretch(1, 1);
    int row = 0;
    if (m_identities.size() > 1) {
        m_identityCombo = new QComboBox(this);
        for (const Identity &id : m_identities)
            m_identityCombo->addItem(identityName(id));
        grid->addWidget(new QLabel(tr("Identity:"), this), row, 0);
        grid->addWidget(m_identityCombo, row, 1);
        ++row;
    } else if (m_identities.size() == 1) {
        grid->addWidget(new QLabel(tr("Authenticating as <b>%1</b>")
                                       .arg(identityName(m_identities.first())),
                                   this),
                        row, 0, 1, 2);
        ++row;
    }
    m_password = new QLineEdit(this);
    m_password->setEchoMode(QLineEdit::Password);
    m_password->setPlaceholderText(tr("Password"));
    grid->addWidget(new QLabel(tr("Password:"), this), row, 0);
    grid->addWidget(m_password, row, 1);
    root->addLayout(grid);

    // Status line (polkit error/info).
    m_status = new QLabel(this);
    m_status->setWordWrap(true);
    m_status->hide();
    root->addWidget(m_status);

    // Buttons.
    auto *buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel,
                                         this);
    m_ok = buttons->button(QDialogButtonBox::Ok);
    m_ok->setText(tr("Authenticate"));
    connect(buttons, &QDialogButtonBox::accepted, this, &QDialog::accept);
    connect(buttons, &QDialogButtonBox::rejected, this, &QDialog::reject);
    root->addWidget(buttons);

    Q_UNUSED(actionId);
    m_password->setFocus();
    resize(420, sizeHint().height());
}

QString AuthDialog::password() const {
    return m_password->text();
}

PolkitQt1::Identity AuthDialog::selectedIdentity() const {
    if (m_identities.isEmpty())
        return Identity();
    const int i = m_identityCombo ? m_identityCombo->currentIndex() : 0;
    return m_identities.value(i, m_identities.first());
}

void AuthDialog::setError(const QString &text) {
    m_status->setText(text);
    m_status->setStyleSheet(QStringLiteral("color:#d9765b;"));
    m_status->setVisible(!text.isEmpty());
}

void AuthDialog::setInfo(const QString &text) {
    m_status->setText(text);
    m_status->setStyleSheet(QString());
    m_status->setVisible(!text.isEmpty());
}

void AuthDialog::clearPassword() {
    m_password->clear();
    m_password->setFocus();
}

void AuthDialog::setBusy(bool busy) {
    m_password->setEnabled(!busy);
    if (m_identityCombo)
        m_identityCombo->setEnabled(!busy);
    if (m_ok)
        m_ok->setEnabled(!busy);
}
