#include "notifyservice.h"

#include "history.h"
#include "toast.h"
#include "petbridge.h"

#include <QDateTime>

namespace helm {

NotifyService::NotifyService(ToastStack *toasts, QObject *parent, const QString &historyPath)
    : QObject(parent), m_toasts(toasts),
      m_historyPath(historyPath.isEmpty() ? defaultHistoryPath() : historyPath) {
    m_history = loadHistory(m_historyPath); // restore the log across restarts
    if (m_toasts) {
        // When a toast expires or is clicked, forget it from the ACTIVE store
        // (the history keeps it) and relay the D-Bus signals.
        connect(m_toasts, &ToastStack::dismissed, this, [this](uint id, uint reason) {
            dropNotification(m_store, id);
            emit closed(id, reason);
        });
        connect(m_toasts, &ToastStack::actionInvoked, this, &NotifyService::actionInvoked);
    }
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
    n.received = QDateTime::currentDateTime();

    putNotification(m_store, n); // the active set (drives toasts, drops on dismiss)

    // The durable log — kept even under DND and past the toast's life. Persist so
    // it survives a daemon restart, then let clients (Lantern) know it grew.
    appendHistory(m_history, n, kHistoryCap);
    saveHistory(m_historyPath, m_history);
    emit added(n);

    if (shouldShowToast(m_dnd, urgency)) {
        if (m_toasts)
            m_toasts->showNotification(n);
        petNotify(n); // and let Hiedi's pet present it (no-op if she isn't running)
    } else if (m_toasts) {
        m_toasts->closeNotification(n.id); // if it was showing (e.g. replaces_id)
    }
    return n.id;
}

void NotifyService::clearHistory() {
    m_history.clear();
    saveHistory(m_historyPath, m_history);
    emit historyCleared();
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
    if (m_toasts)
        m_toasts->closeNotification(id);
    emit closed(id, reason);
}

} // namespace helm
