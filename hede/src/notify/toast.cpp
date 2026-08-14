#include "toast.h"

#include <QFont>
#include <QFrame>
#include <QLabel>
#include <QMouseEvent>
#include <QTimer>
#include <QVBoxLayout>

#include <functional>

namespace helm {

namespace {

// One clickable card. Uses a plain callback (no moc needed) for the click.
class ToastCard : public QFrame {
  public:
    ToastCard(const Notification &n, QWidget *parent) : QFrame(parent) {
        setFrameShape(QFrame::StyledPanel);
        setMinimumWidth(300);
        auto *v = new QVBoxLayout(this);
        v->setContentsMargins(10, 8, 10, 8);
        v->setSpacing(2);
        auto *title = new QLabel(n.summary, this);
        QFont f = title->font();
        f.setBold(true);
        title->setFont(f);
        v->addWidget(title);
        if (!n.body.isEmpty()) {
            auto *body = new QLabel(n.body, this);
            body->setWordWrap(true);
            body->setTextFormat(Qt::RichText);
            v->addWidget(body);
        }
    }
    std::function<void()> onClick;

  protected:
    void mouseReleaseEvent(QMouseEvent *e) override {
        if (e->button() == Qt::LeftButton && onClick)
            onClick();
        QFrame::mouseReleaseEvent(e);
    }
};

bool hasDefaultAction(const QStringList &actions) {
    // actions are (key, label) pairs; a "default" key means click-to-activate.
    for (int i = 0; i + 1 < actions.size(); i += 2)
        if (actions[i] == QLatin1String("default"))
            return true;
    return false;
}

} // namespace

ToastStack::ToastStack(QWidget *parent) : QWidget(parent) {
    m_layout = new QVBoxLayout(this);
    m_layout->setContentsMargins(0, 0, 0, 0);
    m_layout->setSpacing(6);
}

void ToastStack::showNotification(const Notification &n) {
    closeNotification(n.id); // replace if it already exists

    auto *card = new ToastCard(n, this);
    const uint id = n.id;
    const bool def = hasDefaultAction(n.actions);
    card->onClick = [this, id, def] { userClicked(id, def); };
    m_layout->addWidget(card);
    m_cards.insert(id, card);

    if (n.timeoutMs > 0) {
        auto *t = new QTimer(this);
        t->setSingleShot(true);
        connect(t, &QTimer::timeout, this, [this, id] { expire(id); });
        t->start(n.timeoutMs);
        m_timers.insert(id, t);
    }
}

void ToastStack::closeNotification(uint id) {
    if (auto *t = m_timers.take(id))
        t->deleteLater();
    if (auto *c = m_cards.take(id))
        c->deleteLater();
}

void ToastStack::expire(uint id) {
    closeNotification(id);
    emit dismissed(id, 1); // expired
}

void ToastStack::userClicked(uint id, bool hasDefault) {
    if (hasDefault)
        emit actionInvoked(id, QStringLiteral("default"));
    closeNotification(id);
    emit dismissed(id, 2); // dismissed by user
}

} // namespace helm
