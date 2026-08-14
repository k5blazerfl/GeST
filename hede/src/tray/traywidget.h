#pragma once

#include <QHash>
#include <QWidget>

class QHBoxLayout;

namespace helm {

class SniWatcher;
class TrayItem;

// The panel's system-tray applet: hosts a StatusNotifierWatcher, registers as a
// host, and shows one TrayItem per registered StatusNotifierItem.
class TrayWidget : public QWidget {
    Q_OBJECT
  public:
    explicit TrayWidget(QWidget *parent = nullptr);

  private slots:
    void onItemRegistered(const QString &key);
    void onItemUnregistered(const QString &key);
    void onNameOwnerChanged(const QString &name, const QString &oldOwner, const QString &newOwner);

  private:
    SniWatcher *m_watcher;
    QHBoxLayout *m_layout;
    QHash<QString, TrayItem *> m_items;
};

} // namespace helm
