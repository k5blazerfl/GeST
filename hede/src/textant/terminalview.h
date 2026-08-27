#pragma once

#include <QWidget>
#include <QFont>
#include <QPoint>

class VTermSession;
class Pty;

// The terminal surface: paints the libvterm screen (plus scrollback) cell by
// cell, turns key presses into libvterm input, and handles wheel scrollback,
// mouse selection and clipboard. Resizing recomputes the row/column grid.
//
// Line addressing uses an absolute "position": 0..scrollbackCount-1 index the
// scrolled-off history (oldest first); scrollbackCount..scrollbackCount+rows-1
// index the live screen. A viewport row maps to a position via the scroll offset.
class TerminalView : public QWidget {
    Q_OBJECT
public:
    explicit TerminalView(QWidget *parent = nullptr);

    void setSession(VTermSession *session);
    void setPty(Pty *pty) { m_pty = pty; }
    void applyFont(const QString &family, int pointSize);

protected:
    void paintEvent(QPaintEvent *ev) override;
    void keyPressEvent(QKeyEvent *ev) override;
    void resizeEvent(QResizeEvent *ev) override;
    void wheelEvent(QWheelEvent *ev) override;
    void mousePressEvent(QMouseEvent *ev) override;
    void mouseMoveEvent(QMouseEvent *ev) override;
    void mouseReleaseEvent(QMouseEvent *ev) override;
    QSize sizeHint() const override;

private:
    void updateFontMetrics();
    void syncGrid();
    QRect cellsToPixels(const QRect &cells) const;
    int viewportRowToPos(int row) const;
    QPoint pixelToCell(const QPoint &p) const;    // -> (col, pos)
    void setScrollOffset(int off);
    void scrollToBottom() { setScrollOffset(0); }
    bool inSelection(int pos, int col) const;
    QString selectionText() const;
    void copySelection(bool toPrimary);
    void paste(bool fromPrimary);

    VTermSession *m_session = nullptr;
    Pty *m_pty = nullptr;
    QFont m_font;
    int m_cellW = 8;
    int m_cellH = 16;
    int m_ascent = 12;
    int m_scrollOffset = 0;        // lines scrolled up from the live bottom

    bool m_selecting = false;
    bool m_hasSel = false;
    QPoint m_selAnchor { 0, 0 };   // (col, pos)
    QPoint m_selPoint { 0, 0 };    // (col, pos)
};
