#pragma once

#include <QObject>
#include <QByteArray>
#include <QColor>
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

    VTermPos cursor() const { return m_cursor; }
    bool cursorVisible() const { return m_cursorVisible; }

    // Scrollback (P1): lines that have scrolled off the top, oldest first.
    void setScrollbackMax(int lines) { m_scrollbackMax = lines > 0 ? lines : 0; }
    int scrollbackCount() const { return static_cast<int>(m_scrollback.size()); }
    bool scrollbackCell(int line, int col, VTermScreenCell &out) const;

signals:
    void outputReady(const QByteArray &bytes);   // vterm -> pty
    void damaged(const QRect &cellRect);
    void cursorMoved(const QRect &oldCell, const QRect &newCell);
    void bell();
    void titleChanged(const QString &title);
    void lineScrolledOff();                       // a line moved into scrollback

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

    VTerm *m_vt = nullptr;
    VTermScreen *m_screen = nullptr;
    int m_rows;
    int m_cols;
    VTermPos m_cursor { 0, 0 };
    bool m_cursorVisible = true;
    QByteArray m_title;      // accumulates title string fragments
    std::deque<std::vector<VTermScreenCell>> m_scrollback;
    int m_scrollbackMax = 1000;
};
