#pragma once

#include <QString>
#include <QToolButton>

namespace helm {

// One system-tray icon backed by a remote org.kde.StatusNotifierItem.
// Left-click → Activate; right-click → ContextMenu (the app shows its own menu).
class TrayItem : public QToolButton {
    Q_OBJECT
  public:
    TrayItem(const QString &service, const QString &path, QWidget *parent = nullptr);

  private slots:
    void refresh();

  protected:
    void mouseReleaseEvent(QMouseEvent *e) override;

  private:
    QString m_service;
    QString m_path;
};

} // namespace helm
