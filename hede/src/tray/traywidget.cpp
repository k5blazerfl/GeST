#include "traywidget.h"

#include "snimodel.h"
#include "sniwatcher.h"
#include "trayitem.h"

#include <QCoreApplication>
#include <QDBusConnection>
#include <QDBusConnectionInterface>
#include <QHBoxLayout>

namespace helm {

TrayWidget::TrayWidget(QWidget *parent) : QWidget(parent), m_watcher(new SniWatcher(this)) {
    m_layout = new QHBoxLayout(this);
    m_layout->setContentsMargins(2, 0, 2, 0);
    m_layout->setSpacing(2);

    new SniWatcherAdaptor(m_watcher); // parented to m_watcher

    QDBusConnection bus = QDBusConnection::sessionBus();
    bus.registerObject(QStringLiteral("/StatusNotifierWatcher"), m_watcher);
    bus.registerService(QStringLiteral("org.kde.StatusNotifierWatcher"));

    // Register ourselves as a host so items know a host is present.
    m_watcher->setHostRegistered();
    const QString host = hostName(QCoreApplication::applicationPid());
    bus.registerService(host);

    connect(m_watcher, &SniWatcher::itemRegistered, this, &TrayWidget::onItemRegistered);
    connect(m_watcher, &SniWatcher::itemUnregistered, this, &TrayWidget::onItemUnregistered);

    // Drop an app's items when it leaves the bus.
    connect(bus.interface(), &QDBusConnectionInterface::NameOwnerChanged, this,
            &TrayWidget::onNameOwnerChanged);
}

void TrayWidget::onItemRegistered(const QString &key) {
    if (m_items.contains(key))
        return;
    const SniId id = splitKey(key);
    auto *item = new TrayItem(id.service, id.path, this);
    m_layout->addWidget(item);
    m_items.insert(key, item);
}

void TrayWidget::onItemUnregistered(const QString &key) {
    if (auto *item = m_items.take(key))
        item->deleteLater();
}

void TrayWidget::onNameOwnerChanged(const QString &name, const QString &oldOwner,
                                    const QString &newOwner) {
    if (newOwner.isEmpty() && !oldOwner.isEmpty())
        m_watcher->dropService(name);
}

} // namespace helm
