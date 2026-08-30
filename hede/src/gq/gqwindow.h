// General Quarters — the Ctrl+Alt+Del interrupt surface
// (docs/design/hede-session-supervision.md). The theming stops at the
// name: a dark scrim over the desktop and one centered column of plain
// verbs — Lock, Task Manager, Sign out, Restart, Shut down, Cancel.
// Power/session verbs go through logind on the system bus.
#pragma once

#include <QWidget>

namespace helm {

class GqWindow : public QWidget {
    Q_OBJECT
public:
    GqWindow();

protected:
    void paintEvent(QPaintEvent *event) override;
    void keyPressEvent(QKeyEvent *event) override;
    void mousePressEvent(QMouseEvent *event) override;

private:
    void lockScreen();
    void openTaskManager();
    void signOut();
    void logindCall(const QString &method);

    QWidget *card_ = nullptr;
};

} // namespace helm
