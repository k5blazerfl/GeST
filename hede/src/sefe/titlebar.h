#pragma once

#include <QWidget>

class QLabel;

namespace helm::sefe {

// The client-side titlebar for SeFE's frameless scene chrome (Phase D). SeFE
// paints its own window frame so the world scene can span titlebar → menu →
// toolbar → body → status as one region, which means it must also draw the
// titlebar Qt/labwc would normally provide: an app title plus the min / maximize
// / close controls, on the right (Windows-familiar — see the HeDE familiarity
// north-star). Dragging it moves the window (xdg_toplevel move via
// QWindow::startSystemMove); a double-click toggles maximize.
class HelmTitleBar : public QWidget {
    Q_OBJECT
public:
    explicit HelmTitleBar(QWidget *parent = nullptr);
    void setTitle(const QString &title);

protected:
    void mousePressEvent(QMouseEvent *event) override;
    void mouseDoubleClickEvent(QMouseEvent *event) override;

private:
    void toggleMaximize();
    QLabel *_title = nullptr;
};

} // namespace helm::sefe
