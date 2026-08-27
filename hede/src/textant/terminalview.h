#pragma once

#include <QWidget>
#include <QFont>

class VTermSession;
class Pty;

// The terminal surface: a QWidget that paints the libvterm screen model cell by
// cell (monospace, damage-scoped repaints) and turns key presses into libvterm
// input. Resizing recomputes the row/column grid and pushes it to both the
// session and the pty.
class TerminalView : public QWidget {
    Q_OBJECT
public:
    explicit TerminalView(QWidget *parent = nullptr);

    void setSession(VTermSession *session);
    void setPty(Pty *pty) { m_pty = pty; }

protected:
    void paintEvent(QPaintEvent *ev) override;
    void keyPressEvent(QKeyEvent *ev) override;
    void resizeEvent(QResizeEvent *ev) override;
    QSize sizeHint() const override;

private:
    void updateFontMetrics();
    void syncGrid();
    QRect cellsToPixels(const QRect &cells) const;

    VTermSession *m_session = nullptr;
    Pty *m_pty = nullptr;
    QFont m_font;
    int m_cellW = 8;
    int m_cellH = 16;
    int m_ascent = 12;
};
