#include "gqwindow.h"

#include "launch.h"

#include <QApplication>
#include <QDBusConnection>
#include <QDBusInterface>
#include <QHBoxLayout>
#include <QKeyEvent>
#include <QPainter>
#include <QPushButton>
#include <QVBoxLayout>

namespace helm {

namespace {
const QString kLogind = QStringLiteral("org.freedesktop.login1");
const QString kLogindPath = QStringLiteral("/org/freedesktop/login1");
const QString kManager = QStringLiteral("org.freedesktop.login1.Manager");
} // namespace

GqWindow::GqWindow() {
    setAttribute(Qt::WA_TranslucentBackground);

    // The verb column: a plain card centered on the scrim.
    card_ = new QWidget(this);
    card_->setObjectName(QStringLiteral("gqCard"));
    card_->setAutoFillBackground(true);
    auto *column = new QVBoxLayout(card_);
    column->setContentsMargins(24, 24, 24, 24);
    column->setSpacing(10);

    auto addVerb = [&](const QString &text, auto slot) {
        auto *button = new QPushButton(text, card_);
        button->setMinimumHeight(44);
        connect(button, &QPushButton::clicked, this, slot);
        column->addWidget(button);
        return button;
    };
    QPushButton *lock = addVerb(tr("Lock"), [this] { lockScreen(); });
    addVerb(tr("Task Manager"), [this] { openTaskManager(); });
    column->addSpacing(8);
    addVerb(tr("Sign out"), [this] { signOut(); });
    addVerb(tr("Restart"), [this] { logindCall(QStringLiteral("Reboot")); });
    addVerb(tr("Shut down"), [this] { logindCall(QStringLiteral("PowerOff")); });
    column->addSpacing(8);
    addVerb(tr("Cancel"), [] { QApplication::quit(); });
    lock->setFocus();

    // Center the card whatever the surface size ends up being.
    auto *rows = new QVBoxLayout(this);
    auto *middle = new QHBoxLayout;
    rows->addStretch(1);
    middle->addStretch(1);
    middle->addWidget(card_);
    card_->setFixedWidth(340);
    middle->addStretch(1);
    rows->addLayout(middle);
    rows->addStretch(1);
}

void GqWindow::paintEvent(QPaintEvent *) {
    // The scrim: the desktop stays visible but clearly interrupted.
    QPainter painter(this);
    painter.setCompositionMode(QPainter::CompositionMode_Source);
    painter.fillRect(rect(), QColor(0, 0, 0, 150));
}

void GqWindow::keyPressEvent(QKeyEvent *event) {
    if (event->key() == Qt::Key_Escape) {
        QApplication::quit();
        return;
    }
    QWidget::keyPressEvent(event);
}

void GqWindow::mousePressEvent(QMouseEvent *event) {
    // A click on the scrim (outside the card) dismisses, like Esc.
    if (!card_->geometry().contains(event->pos()))
        QApplication::quit();
}

void GqWindow::lockScreen() {
    launchDetached(QStringLiteral("swaylock"), {QStringLiteral("-f")});
    QApplication::quit();
}

void GqWindow::openTaskManager() {
    launchDetached(QStringLiteral("ezra"));
    QApplication::quit();
}

void GqWindow::signOut() {
    const QString sessionId = qEnvironmentVariable("XDG_SESSION_ID");
    if (!sessionId.isEmpty()) {
        QDBusInterface manager(kLogind, kLogindPath, kManager, QDBusConnection::systemBus());
        manager.call(QStringLiteral("TerminateSession"), sessionId);
    } else {
        // No logind session id (broken login path): fall back to ending the
        // compositor, which ends the session the blunt way.
        launchDetached(QStringLiteral("pkill"), {QStringLiteral("-x"), QStringLiteral("labwc")});
    }
    QApplication::quit();
}

void GqWindow::logindCall(const QString &method) {
    // interactive=true lets polkit prompt if policy wants auth for
    // multi-user cases; the common single-active-session case is allowed.
    QDBusInterface manager(kLogind, kLogindPath, kManager, QDBusConnection::systemBus());
    manager.call(method, true);
    QApplication::quit();
}

} // namespace helm
