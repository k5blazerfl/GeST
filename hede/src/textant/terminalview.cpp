#include "terminalview.h"

#include "pty.h"
#include "vtermsession.h"

#include <QFontMetrics>
#include <QKeyEvent>
#include <QPainter>
#include <QPaintEvent>
#include <QResizeEvent>

#include <algorithm>

namespace {
const QColor kBackground(0x0e, 0x17, 0x28);
const QColor kCursor(0xff, 0xc2, 0x47);
}

TerminalView::TerminalView(QWidget *parent) : QWidget(parent) {
    setFocusPolicy(Qt::StrongFocus);
    setAttribute(Qt::WA_OpaquePaintEvent);

    m_font = QFont(QStringLiteral("monospace"), 11);
    m_font.setStyleHint(QFont::Monospace);
    m_font.setFixedPitch(true);
    updateFontMetrics();
}

void TerminalView::setSession(VTermSession *session) {
    m_session = session;
    if (!session)
        return;
    connect(session, &VTermSession::damaged, this, [this](const QRect &cells) {
        update(cellsToPixels(cells));
    });
    connect(session, &VTermSession::cursorMoved, this,
            [this](const QRect &oldCell, const QRect &newCell) {
                update(cellsToPixels(oldCell));
                update(cellsToPixels(newCell));
            });
    update();
}

void TerminalView::updateFontMetrics() {
    const QFontMetrics fm(m_font);
    m_cellW = std::max(1, fm.horizontalAdvance(QChar('M')));
    m_cellH = std::max(1, fm.height());
    m_ascent = fm.ascent();
}

void TerminalView::syncGrid() {
    if (m_cellW <= 0 || m_cellH <= 0)
        return;
    const int cols = std::max(1, width() / m_cellW);
    const int rows = std::max(1, height() / m_cellH);
    if (m_session)
        m_session->setSize(rows, cols);
    if (m_pty)
        m_pty->resize(rows, cols);
    update();
}

QRect TerminalView::cellsToPixels(const QRect &c) const {
    return QRect(c.x() * m_cellW, c.y() * m_cellH,
                 c.width() * m_cellW, c.height() * m_cellH);
}

QSize TerminalView::sizeHint() const {
    return QSize(m_cellW * 80, m_cellH * 24);
}

void TerminalView::resizeEvent(QResizeEvent *) {
    syncGrid();
}

void TerminalView::paintEvent(QPaintEvent *ev) {
    QPainter p(this);
    p.fillRect(ev->rect(), kBackground);
    if (!m_session)
        return;

    const int rows = m_session->rows();
    const int cols = m_session->cols();
    const QRect clip = ev->rect();
    const int c0 = std::max(0, clip.left() / m_cellW);
    const int c1 = std::min(cols - 1, clip.right() / m_cellW);
    const int r0 = std::max(0, clip.top() / m_cellH);
    const int r1 = std::min(rows - 1, clip.bottom() / m_cellH);

    for (int r = r0; r <= r1; ++r) {
        for (int c = c0; c <= c1; ++c) {
            VTermScreenCell cell;
            if (!m_session->cell(r, c, cell))
                continue;
            if (cell.width == 0)     // right half of a wide glyph — already drawn
                continue;

            const int x = c * m_cellW;
            const int y = r * m_cellH;
            const int w = m_cellW * (cell.width > 0 ? cell.width : 1);

            QColor fg = m_session->toColor(cell.fg);
            QColor bg = m_session->toColor(cell.bg);
            if (cell.attrs.reverse)
                std::swap(fg, bg);

            if (bg != kBackground)
                p.fillRect(x, y, w, m_cellH, bg);

            int n = 0;
            while (n < VTERM_MAX_CHARS_PER_CELL && cell.chars[n])
                ++n;
            if (n > 0) {
                const QString s = QString::fromUcs4(
                    reinterpret_cast<const char32_t *>(cell.chars), n);
                if (cell.attrs.bold || cell.attrs.italic || cell.attrs.underline) {
                    QFont f = m_font;
                    f.setBold(cell.attrs.bold);
                    f.setItalic(cell.attrs.italic);
                    f.setUnderline(cell.attrs.underline);
                    p.setFont(f);
                } else {
                    p.setFont(m_font);
                }
                p.setPen(fg);
                p.drawText(x, y + m_ascent, s);
            }
        }
    }

    if (m_session->cursorVisible()) {
        const VTermPos cur = m_session->cursor();
        if (cur.row >= 0 && cur.row < rows && cur.col >= 0 && cur.col < cols) {
            QColor c = kCursor;
            c.setAlpha(180);
            p.fillRect(cur.col * m_cellW, cur.row * m_cellH, m_cellW, m_cellH, c);
        }
    }
}

void TerminalView::keyPressEvent(QKeyEvent *ev) {
    if (!m_session)
        return;

    VTermModifier mod = VTERM_MOD_NONE;
    const Qt::KeyboardModifiers qm = ev->modifiers();
    if (qm & Qt::ShiftModifier)
        mod = static_cast<VTermModifier>(mod | VTERM_MOD_SHIFT);
    if (qm & Qt::AltModifier)
        mod = static_cast<VTermModifier>(mod | VTERM_MOD_ALT);
    if (qm & Qt::ControlModifier)
        mod = static_cast<VTermModifier>(mod | VTERM_MOD_CTRL);

    // Special keys first.
    VTermKey vk = VTERM_KEY_NONE;
    switch (ev->key()) {
    case Qt::Key_Return:
    case Qt::Key_Enter:     vk = VTERM_KEY_ENTER; break;
    case Qt::Key_Backspace: vk = VTERM_KEY_BACKSPACE; break;
    case Qt::Key_Tab:       vk = VTERM_KEY_TAB; break;
    case Qt::Key_Escape:    vk = VTERM_KEY_ESCAPE; break;
    case Qt::Key_Up:        vk = VTERM_KEY_UP; break;
    case Qt::Key_Down:      vk = VTERM_KEY_DOWN; break;
    case Qt::Key_Left:      vk = VTERM_KEY_LEFT; break;
    case Qt::Key_Right:     vk = VTERM_KEY_RIGHT; break;
    case Qt::Key_Home:      vk = VTERM_KEY_HOME; break;
    case Qt::Key_End:       vk = VTERM_KEY_END; break;
    case Qt::Key_PageUp:    vk = VTERM_KEY_PAGEUP; break;
    case Qt::Key_PageDown:  vk = VTERM_KEY_PAGEDOWN; break;
    case Qt::Key_Insert:    vk = VTERM_KEY_INS; break;
    case Qt::Key_Delete:    vk = VTERM_KEY_DEL; break;
    default: break;
    }
    if (ev->key() >= Qt::Key_F1 && ev->key() <= Qt::Key_F35)
        vk = static_cast<VTermKey>(VTERM_KEY_FUNCTION(1) + (ev->key() - Qt::Key_F1));

    if (vk != VTERM_KEY_NONE) {
        m_session->inputKey(vk, mod);
        return;
    }

    // Ctrl+letter: hand libvterm the base letter so it encodes the control byte.
    if (qm & Qt::ControlModifier) {
        const int k = ev->key();
        if (k >= Qt::Key_A && k <= Qt::Key_Z) {
            m_session->inputChar(static_cast<uint32_t>(k - Qt::Key_A + 'a'), mod);
            return;
        }
        if (k == Qt::Key_Space) {
            m_session->inputChar(' ', mod);
            return;
        }
    }

    // Printable text — already reflects Shift, so pass without modifiers.
    const QString text = ev->text();
    if (!text.isEmpty()) {
        const auto ucs = text.toUcs4();
        for (uint c : ucs)
            if (c >= 0x20)
                m_session->inputChar(c, VTERM_MOD_NONE);
    }
}
