#include "sniwatcher.h"

#include "snimodel.h"

#include <QDBusMessage>

namespace helm {

// ---------------- store ----------------

SniWatcher::SniWatcher(QObject *parent) : QObject(parent) {}

void SniWatcher::registerItem(const QString &key) {
    if (addUnique(m_items, key))
        emit itemRegistered(key);
}

void SniWatcher::setHostRegistered() {
    if (!m_hostRegistered) {
        m_hostRegistered = true;
        emit hostRegisteredChanged();
    }
}

void SniWatcher::dropService(const QString &uniqueName) {
    const QStringList current = m_items;
    for (const QString &key : current) {
        if (splitKey(key).service == uniqueName && removeOne(m_items, key))
            emit itemUnregistered(key);
    }
}

// ---------------- adaptor ----------------

SniWatcherAdaptor::SniWatcherAdaptor(SniWatcher *watcher)
    : QDBusAbstractAdaptor(watcher), m_watcher(watcher) {
    connect(watcher, &SniWatcher::itemRegistered, this,
            &SniWatcherAdaptor::StatusNotifierItemRegistered);
    connect(watcher, &SniWatcher::itemUnregistered, this,
            &SniWatcherAdaptor::StatusNotifierItemUnregistered);
    connect(watcher, &SniWatcher::hostRegisteredChanged, this,
            &SniWatcherAdaptor::StatusNotifierHostRegistered);
}

QStringList SniWatcherAdaptor::registeredStatusNotifierItems() const {
    return m_watcher->items();
}

bool SniWatcherAdaptor::isStatusNotifierHostRegistered() const {
    return m_watcher->hostRegistered();
}

void SniWatcherAdaptor::RegisterStatusNotifierItem(const QString &service) {
    const QString sender = calledFromDBus() ? message().service() : QString();
    m_watcher->registerItem(parseItemService(service, sender).key());
}

void SniWatcherAdaptor::RegisterStatusNotifierHost(const QString &) {
    m_watcher->setHostRegistered();
}

} // namespace helm
