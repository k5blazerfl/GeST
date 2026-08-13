#pragma once

#include <QPushButton>
#include <QString>

namespace helm {

// A button that spawns a shell command (the configured terminal, in Phase 0).
class LauncherButton : public QPushButton {
    Q_OBJECT
  public:
    LauncherButton(const QString &text, const QString &command, QWidget *parent = nullptr);

  private:
    QString m_command;
};

} // namespace helm
