#pragma once

#include <QDBusAbstractAdaptor>
#include <QDBusContext>
#include <QObject>
#include <QStringList>

namespace helm {

// Backing store + logic for the StatusNotifierWatcher.
class SniWatcher : public QObject {
    Q_OBJECT
  public:
    explicit SniWatcher(QObject *parent = nullptr);

    QStringList items() const { return m_items; }
    bool hostRegistered() const { return m_hostRegistered; }

    void registerItem(const QString &key);
    void setHostRegistered();
    void dropService(const QString &uniqueName); // an app left the bus

  signals:
    void itemRegistered(const QString &key);
    void itemUnregistered(const QString &key);
    void hostRegisteredChanged();

  private:
    QStringList m_items;
    bool m_hostRegistered = false;
};

// org.kde.StatusNotifierWatcher D-Bus interface.
class SniWatcherAdaptor : public QDBusAbstractAdaptor, protected QDBusContext {
    Q_OBJECT
    Q_CLASSINFO("D-Bus Interface", "org.kde.StatusNotifierWatcher")
    Q_PROPERTY(QStringList RegisteredStatusNotifierItems READ registeredStatusNotifierItems)
    Q_PROPERTY(bool IsStatusNotifierHostRegistered READ isStatusNotifierHostRegistered)
    Q_PROPERTY(int ProtocolVersion READ protocolVersion)
  public:
    explicit SniWatcherAdaptor(SniWatcher *watcher);

    QStringList registeredStatusNotifierItems() const;
    bool isStatusNotifierHostRegistered() const;
    int protocolVersion() const { return 0; }

  public slots: // NOLINT — D-Bus method names must match the spec
    void RegisterStatusNotifierItem(const QString &service);
    void RegisterStatusNotifierHost(const QString &service);

  signals:
    void StatusNotifierItemRegistered(const QString &service);
    void StatusNotifierItemUnregistered(const QString &service);
    void StatusNotifierHostRegistered();

  private:
    SniWatcher *m_watcher;
};

} // namespace helm
