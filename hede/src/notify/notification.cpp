#include "notification.h"

namespace helm {

uint nextNotificationId(uint last) {
    return (last == 0xffffffffu) ? 1u : last + 1u;
}

int resolveTimeout(int expireTimeout, int defaultMs) {
    if (expireTimeout < 0)
        return defaultMs;
    return expireTimeout; // 0 (persist) or explicit ms
}

QStringList serverCapabilities() {
    return {QStringLiteral("body"), QStringLiteral("actions"), QStringLiteral("icon-static"),
            QStringLiteral("body-markup")};
}

int indexOfId(const QVector<Notification> &list, uint id) {
    for (int i = 0; i < list.size(); ++i)
        if (list[i].id == id)
            return i;
    return -1;
}

void putNotification(QVector<Notification> &list, const Notification &n) {
    const int i = indexOfId(list, n.id);
    if (i < 0)
        list.append(n);
    else
        list[i] = n;
}

void dropNotification(QVector<Notification> &list, uint id) {
    const int i = indexOfId(list, id);
    if (i >= 0)
        list.remove(i);
}

} // namespace helm
