#include "notifyservice.h"

#include "toast.h"

namespace helm {

NotifyService::NotifyService(ToastStack *toasts, QObject *parent)
    : QObject(parent), m_toasts(toasts) {
    // When a toast expires or is clicked, forget it and relay the D-Bus signals.
    connect(m_toasts, &ToastStack::dismissed, this, [this](uint id, uint reason) {
        dropNotification(m_store, id);
        emit closed(id, reason);
    });
    connect(m_toasts, &ToastStack::actionInvoked, this, &NotifyService::actionInvoked);
}

uint NotifyService::notify(const QString &app, uint replacesId, const QString &icon,
                           const QString &summary, const QString &body, const QStringList &actions,
                           int expireTimeout, int urgency) {
    Notification n;
    n.id = replacesId != 0 ? replacesId : (m_lastId = nextNotificationId(m_lastId));
    n.app = app;
    n.icon = icon;
    n.summary = summary;
    n.body = body;
    n.actions = actions;
    n.timeoutMs = resolveTimeout(expireTimeout, kDefaultTimeoutMs);
    n.urgency = urgency;

    putNotification(m_store, n); // always tracked (history), even under DND
    if (shouldShowToast(m_dnd, urgency))
        m_toasts->showNotification(n);
    else
        m_toasts->closeNotification(n.id); // if it was showing (e.g. replaces_id)
    return n.id;
}

void NotifyService::setDoNotDisturb(bool on) {
    if (m_dnd == on)
        return;
    m_dnd = on;
    emit dndChanged(on);
}

void NotifyService::closeNotification(uint id, uint reason) {
    if (indexOfId(m_store, id) < 0)
        return;
    dropNotification(m_store, id);
    m_toasts->closeNotification(id);
    emit closed(id, reason);
}

} // namespace helm
