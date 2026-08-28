#pragma once

#include <QObject>
#include <QByteArray>
#include <QColor>
#include <QImage>
#include <QRect>
#include <QString>

#include <deque>
#include <vector>

extern "C" {
#include <vterm.h>
}

// Wraps a libvterm instance + its screen buffer. Pty output is fed in via
// writeInput(); libvterm parses it, maintains the screen model, and fires the
// callbacks below (re-emitted as Qt signals). Keyboard input is encoded back out
// through libvterm and surfaces as outputReady() for the pty.
class VTermSession : public QObject {
    Q_OBJECT
public:
    VTermSession(int rows, int cols, QObject *parent = nullptr);
    ~VTermSession() override;

    void writeInput(const QByteArray &bytes);    // pty -> vterm
    void setSize(int rows, int cols);

    void inputChar(uint32_t c, VTermModifier mod);
    void inputKey(VTermKey key, VTermModifier mod);

    int rows() const { return m_rows; }
    int cols() const { return m_cols; }
    bool cell(int row, int col, VTermScreenCell &out) const;
    QColor toColor(VTermColor col) const;        // resolves indexed/default -> rgb

    // Default fg/bg (world-tinted by the caller; drives the unset-colour cells
    // and the surface clear). Repaints on change.
    void setDefaultColors(const QColor &fg, const QColor &bg);
    QColor defaultFg() const { return m_defaultFg; }
    QColor defaultBg() const { return m_defaultBg; }

    VTermPos cursor() const { return m_cursor; }
    bool cursorVisible() const { return m_cursorVisible; }

    // Scrollback (P1): lines that have scrolled off the top, oldest first.
    void setScrollbackMax(int lines) { m_scrollbackMax = lines > 0 ? lines : 0; }
    int scrollbackCount() const { return static_cast<int>(m_scrollback.size()); }
    bool scrollbackCell(int line, int col, VTermScreenCell &out) const;

    // Sixel (P3): the cell pixel height lets the session reserve the right number
    // of text rows below a decoded image.
    void setCellHeight(int px) { if (px > 0) m_cellHeight = px; }

signals:
    void outputReady(const QByteArray &bytes);   // vterm -> pty
    void damaged(const QRect &cellRect);
    void cursorMoved(const QRect &oldCell, const QRect &newCell);
    void bell();
    void titleChanged(const QString &title);
    void lineScrolledOff();                       // a line moved into scrollback
    void imageReceived(const QImage &img, int absPos, int col);   // sixel image

private:
    // libvterm C callbacks (user == this).
    static void onOutput(const char *s, size_t len, void *user);
    static int  onDamage(VTermRect rect, void *user);
    static int  onMoveCursor(VTermPos pos, VTermPos oldpos, int visible, void *user);
    static int  onSetTermProp(VTermProp prop, VTermValue *val, void *user);
    static int  onBell(void *user);
    static int  onResize(int rows, int cols, void *user);
    static int  onPushline(int cols, const VTermScreenCell *cells, void *user);
    static int  onPopline(int cols, VTermScreenCell *cells, void *user);
    static int  onSbClear(void *user);
    static int  onDcs(const char *command, size_t commandlen,
                      VTermStringFragment frag, void *user);

    VTerm *m_vt = nullptr;
    VTermScreen *m_screen = nullptr;
    int m_rows;
    int m_cols;
    VTermPos m_cursor { 0, 0 };
    bool m_cursorVisible = true;
    QByteArray m_title;      // accumulates title string fragments
    std::deque<std::vector<VTermScreenCell>> m_scrollback;
    int m_scrollbackMax = 1000;
    QColor m_defaultFg { 0xe9, 0xee, 0xf6 };
    QColor m_defaultBg { 0x1a, 0x1b, 0x1e };
    QByteArray m_sixelBuf;       // accumulates DCS sixel payload fragments
    bool m_inSixel = false;
    int m_cellHeight = 16;
    int m_pendingRows = 0;       // text rows to advance after an image
};
