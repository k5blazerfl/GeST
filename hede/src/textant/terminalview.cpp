#include "terminalview.h"

#include "pty.h"
#include "vtermsession.h"

#include <QApplication>
#include <QClipboard>
#include <QDesktopServices>
#include <QFontMetrics>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QPainter>
#include <QPaintEvent>
#include <QRegularExpression>
#include <QResizeEvent>
#include <QUrl>
#include <QWheelEvent>

#include <algorithm>

namespace {
const QColor kBackground(0x1a, 0x1b, 0x1e);

QColor blend(const QColor &a, const QColor &b, double t) {
    return QColor(int(a.red() + (b.red() - a.red()) * t),
                  int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t));
}

// Fetch a cell by absolute position (scrollback then live).
bool posCell(const VTermSession *s, int pos, int col, VTermScreenCell &out) {
    const int sb = s->scrollbackCount();
    if (pos < 0 || pos >= sb + s->rows())
        return false;
    if (pos < sb)
        return s->scrollbackCell(pos, col, out);
    return s->cell(pos - sb, col, out);
}

int cellChars(const VTermScreenCell &cell, QString &out) {
    int n = 0;
    while (n < VTERM_MAX_CHARS_PER_CELL && cell.chars[n])
        ++n;
    out = n > 0 ? QString::fromUcs4(reinterpret_cast<const char32_t *>(cell.chars), n)
                : QString();
    return n;
}

// The common single-line box-drawing characters: which cell edges they connect.
bool boxConnections(uint cp, bool &up, bool &down, bool &left, bool &right) {
    up = down = left = right = false;
    switch (cp) {
    case 0x2500: left = right = true; break;               // ─
    case 0x2502: up = down = true; break;                  // │
    case 0x250C: right = down = true; break;               // ┌
    case 0x2510: left = down = true; break;                // ┐
    case 0x2514: up = right = true; break;                 // └
    case 0x2518: up = left = true; break;                  // ┘
    case 0x251C: up = down = right = true; break;          // ├
    case 0x2524: up = down = left = true; break;           // ┤
    case 0x252C: left = right = down = true; break;        // ┬
    case 0x2534: left = right = up = true; break;          // ┴
    case 0x253C: up = down = left = right = true; break;   // ┼
    default: return false;
    }
    return true;
}

// Draw a box-drawing glyph as lines to the cell edges, so adjacent cells join
// into unbroken borders (font glyphs leave gaps / drift).
void drawBoxGlyph(QPainter &p, int x, int y, int w, int h, uint cp, const QColor &color) {
    bool up, down, left, right;
    boxConnections(cp, up, down, left, right);
    const int cx = x + w / 2, cy = y + h / 2;    // integer -> crisp, no AA smear
    QPen pen(color, std::max(1, w / 8));
    pen.setCapStyle(Qt::SquareCap);              // caps overlap the join
    p.save();
    p.setPen(pen);
    // Straight-through runs draw as ONE line (no centre seam per cell, which is
    // what made long borders look faintly dotted); only corners/junctions split.
    if (left && right && !up && !down) {
        p.drawLine(x, cy, x + w, cy);
    } else if (up && down && !left && !right) {
        p.drawLine(cx, y, cx, y + h);
    } else {
        if (left)  p.drawLine(x, cy, cx, cy);
        if (right) p.drawLine(cx, cy, x + w, cy);
        if (up)    p.drawLine(cx, y, cx, cy);
        if (down)  p.drawLine(cx, cy, cx, y + h);
    }
    p.restore();
}
} // namespace

TerminalView::TerminalView(QWidget *parent) : QWidget(parent) {
    setFocusPolicy(Qt::StrongFocus);
    setAttribute(Qt::WA_OpaquePaintEvent);
    setCursor(Qt::IBeamCursor);

    m_font = QFont(QStringLiteral("monospace"), 11);
    m_font.setStyleHint(QFont::Monospace);
    m_font.setFixedPitch(true);
    updateFontMetrics();
}

void TerminalView::setAccent(const QColor &accent) {
    if (!accent.isValid())
        return;
    m_cursorColor = accent;                          // the biome colour, on the cursor
    m_selectionColor = blend(kBackground, accent, 0.5);
    update();
}

void TerminalView::setOpacity(double opacity) {
    m_opacity = std::clamp(opacity, 0.2, 1.0);
    const bool glass = m_opacity < 0.999;
    setAttribute(Qt::WA_TranslucentBackground, glass);
    setAttribute(Qt::WA_OpaquePaintEvent, !glass);
    update();
}

void TerminalView::applyFont(const QString &family, int pointSize) {
    if (!family.isEmpty())
        m_font.setFamily(family);
    if (pointSize > 0)
        m_font.setPointSize(pointSize);
    m_font.setStyleHint(QFont::Monospace);
    m_font.setFixedPitch(true);
    updateFontMetrics();
    syncGrid();
    update();
}

void TerminalView::setSession(VTermSession *session) {
    m_session = session;
    if (!session)
        return;
    connect(session, &VTermSession::damaged, this, [this](const QRect &cells) {
        if (m_scrollOffset > 0)
            update();                       // live coords don't map cleanly when scrolled
        else
            update(cellsToPixels(cells));
    });
    connect(session, &VTermSession::cursorMoved, this,
            [this](const QRect &oldCell, const QRect &newCell) {
                if (m_scrollOffset > 0)
                    return;
                update(cellsToPixels(oldCell));
                update(cellsToPixels(newCell));
            });
    // A line scrolled into history: keep the viewed content stable if scrolled up,
    // and drop any selection (its positions would shift).
    connect(session, &VTermSession::lineScrolledOff, this, [this] {
        if (m_scrollOffset > 0)
            setScrollOffset(m_scrollOffset + 1);
        if (m_hasSel) {
            m_hasSel = false;
            update();
        }
    });
    connect(session, &VTermSession::imageReceived, this,
            [this](const QImage &img, int absPos, int col) {
                m_images.push_back({absPos, col, img});
                if (m_images.size() > 64)          // cap live images
                    m_images.remove(0);
                update();
            });
    session->setCellHeight(m_cellH);
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
    if (m_session) {
        m_session->setSize(rows, cols);
        m_session->setCellHeight(m_cellH);
    }
    if (m_pty)
        m_pty->resize(rows, cols);
    update();
}

QRect TerminalView::cellsToPixels(const QRect &c) const {
    return QRect(c.x() * m_cellW, c.y() * m_cellH,
                 c.width() * m_cellW, c.height() * m_cellH);
}

int TerminalView::viewportRowToPos(int row) const {
    return m_session ? m_session->scrollbackCount() - m_scrollOffset + row : row;
}

QPoint TerminalView::pixelToCell(const QPoint &p) const {
    const int cols = m_session ? m_session->cols() : 1;
    const int rows = m_session ? m_session->rows() : 1;
    const int col = std::clamp(p.x() / m_cellW, 0, cols - 1);
    const int row = std::clamp(p.y() / m_cellH, 0, rows - 1);
    return QPoint(col, viewportRowToPos(row));
}

QString TerminalView::urlAt(int pos, int col) const {
    if (!m_session)
        return QString();
    const int cols = m_session->cols();
    QString line;                       // one char per column, so index == column
    for (int c = 0; c < cols; ++c) {
        VTermScreenCell cell;
        QString ch;
        line += (posCell(m_session, pos, c, cell) && cellChars(cell, ch) > 0)
                    ? ch.left(1)
                    : QStringLiteral(" ");
    }
    static const QRegularExpression re(
        QStringLiteral(R"((?:https?://|www\.)[^\s"'<>()\[\]]+)"));
    auto it = re.globalMatch(line);
    while (it.hasNext()) {
        const QRegularExpressionMatch m = it.next();
        if (col >= m.capturedStart() && col < m.capturedEnd()) {
            QString u = m.captured();
            while (u.endsWith(QLatin1Char('.')) || u.endsWith(QLatin1Char(',')))
                u.chop(1);              // trailing sentence punctuation
            if (u.startsWith(QLatin1String("www.")))
                u.prepend(QStringLiteral("https://"));
            return u;
        }
    }
    return QString();
}

void TerminalView::setScrollOffset(int off) {
    const int maxOff = m_session ? m_session->scrollbackCount() : 0;
    off = std::clamp(off, 0, maxOff);
    if (off == m_scrollOffset)
        return;
    m_scrollOffset = off;
    update();
}

QSize TerminalView::sizeHint() const {
    return QSize(m_cellW * 80, m_cellH * 24);
}

void TerminalView::resizeEvent(QResizeEvent *) {
    syncGrid();
}

void TerminalView::wheelEvent(QWheelEvent *ev) {
    if (!m_session)
        return;
    const int steps = ev->angleDelta().y() / 40;   // ~3 lines per notch
    if (steps != 0)
        setScrollOffset(m_scrollOffset + steps);
    ev->accept();
}

bool TerminalView::inSelection(int pos, int col) const {
    if (!m_hasSel)
        return false;
    QPoint a = m_selAnchor, b = m_selPoint;     // (col, pos)
    const auto before = [](QPoint x, QPoint y) {
        return x.y() < y.y() || (x.y() == y.y() && x.x() < y.x());
    };
    QPoint s = before(a, b) ? a : b;
    QPoint e = before(a, b) ? b : a;
    if (pos < s.y() || pos > e.y())
        return false;
    if (pos == s.y() && col < s.x())
        return false;
    if (pos == e.y() && col > e.x())
        return false;
    return true;
}

void TerminalView::paintEvent(QPaintEvent *ev) {
    QPainter p(this);
    const QColor defBg = m_session ? m_session->defaultBg() : kBackground;
    if (m_opacity < 0.999) {
        QColor glass = defBg;
        glass.setAlphaF(m_opacity);
        p.setCompositionMode(QPainter::CompositionMode_Source);  // write the alpha
        p.fillRect(ev->rect(), glass);
        p.setCompositionMode(QPainter::CompositionMode_SourceOver);
    } else {
        p.fillRect(ev->rect(), defBg);
    }
    if (!m_session)
        return;

    const int rows = m_session->rows();
    const int cols = m_session->cols();
    const QRect clip = ev->rect();
    const int c0 = std::max(0, clip.left() / m_cellW);
    const int c1 = std::min(cols - 1, clip.right() / m_cellW);
    const int r0 = std::max(0, clip.top() / m_cellH);
    const int r1 = std::min(rows - 1, clip.bottom() / m_cellH);

    // Effective fg/bg for a cell (reverse video + selection applied).
    const auto effColors = [this](int pos, int c, const VTermScreenCell &cell,
                                  QColor &fg, QColor &bg) {
        fg = m_session->toColor(cell.fg);
        bg = m_session->toColor(cell.bg);
        if (cell.attrs.reverse)
            std::swap(fg, bg);
        if (inSelection(pos, c))
            bg = m_selectionColor;
    };

    for (int r = r0; r <= r1; ++r) {
        const int pos = viewportRowToPos(r);
        const int y = r * m_cellH;

        // Pass 1 — backgrounds, batching contiguous cells of equal bg.
        for (int c = c0; c <= c1;) {
            VTermScreenCell cell;
            if (!posCell(m_session, pos, c, cell)) { ++c; continue; }
            QColor fg, bg;
            effColors(pos, c, cell, fg, bg);
            int cc = c + 1;
            for (; cc <= c1; ++cc) {
                VTermScreenCell n;
                QColor nf, nb;
                if (!posCell(m_session, pos, cc, n)) break;
                effColors(pos, cc, n, nf, nb);
                if (nb != bg) break;
            }
            if (bg != defBg)
                p.fillRect(c * m_cellW, y, (cc - c) * m_cellW, m_cellH, bg);
            c = cc;
        }

        // Pass 2 — glyphs, batching runs that share fg + attrs (width-1 cells);
        // wide glyphs draw singly.
        for (int c = c0; c <= c1;) {
            VTermScreenCell cell;
            if (!posCell(m_session, pos, c, cell) || cell.width == 0) { ++c; continue; }
            QColor fg, bg;
            effColors(pos, c, cell, fg, bg);
            const bool bold = cell.attrs.bold, ital = cell.attrs.italic,
                       under = cell.attrs.underline;
            QFont f = m_font;
            if (bold || ital || under) {
                f.setBold(bold);
                f.setItalic(ital);
                f.setUnderline(under);
            }
            p.setFont(f);
            p.setPen(fg);

            if (cell.width != 1) {                 // wide glyph
                QString ch;
                if (cellChars(cell, ch) > 0)
                    p.drawText(c * m_cellW, y + m_ascent, ch);
                c += cell.width;
                continue;
            }

            // Same-style run: set font/pen once (above), but draw each glyph at
            // its exact cell x. Drawing the run as one string would let the font's
            // natural advance drift off the grid, so long box-drawing borders
            // wouldn't meet their corners (visible clipping on wide TUIs).
            int cc = c;
            for (; cc <= c1; ++cc) {
                VTermScreenCell n;
                if (!posCell(m_session, pos, cc, n) || n.width != 1) break;
                QColor nf, nb;
                effColors(pos, cc, n, nf, nb);
                if (nf != fg || n.attrs.bold != bold || n.attrs.italic != ital
                    || n.attrs.underline != under)
                    break;
                QString ch;
                if (cellChars(n, ch) > 0 && ch != QStringLiteral(" ")) {
                    bool u, d, l, r;
                    if (boxConnections(n.chars[0], u, d, l, r))
                        drawBoxGlyph(p, cc * m_cellW, y, m_cellW, m_cellH,
                                     n.chars[0], fg);
                    else
                        p.drawText(cc * m_cellW, y + m_ascent, ch);
                }
            }
            c = cc;
        }
    }

    // Sixel images, anchored to their absolute line/column, over the blank cells
    // the session reserved for them.
    if (!m_images.isEmpty()) {
        const int sb = m_session->scrollbackCount();
        for (const PlacedImage &pi : m_images) {
            const int y = (pi.pos - (sb - m_scrollOffset)) * m_cellH;
            if (y + pi.img.height() < 0 || y > height())
                continue;
            p.drawImage(pi.col * m_cellW, y, pi.img);
        }
    }

    if (m_scrollOffset == 0 && m_session->cursorVisible()) {
        const VTermPos cur = m_session->cursor();
        if (cur.row >= 0 && cur.row < rows && cur.col >= 0 && cur.col < cols) {
            QColor c = m_cursorColor;
            c.setAlpha(180);
            p.fillRect(cur.col * m_cellW, cur.row * m_cellH, m_cellW, m_cellH, c);
        }
    }
}

QString TerminalView::selectionText() const {
    if (!m_hasSel || !m_session)
        return QString();
    QPoint a = m_selAnchor, b = m_selPoint;
    const auto before = [](QPoint x, QPoint y) {
        return x.y() < y.y() || (x.y() == y.y() && x.x() < y.x());
    };
    const QPoint s = before(a, b) ? a : b;
    const QPoint e = before(a, b) ? b : a;
    const int cols = m_session->cols();

    QString out;
    for (int pos = s.y(); pos <= e.y(); ++pos) {
        const int from = (pos == s.y()) ? s.x() : 0;
        const int to = (pos == e.y()) ? e.x() : cols - 1;
        QString line;
        for (int c = from; c <= to; ++c) {
            VTermScreenCell cell;
            if (!posCell(m_session, pos, c, cell) || cell.width == 0)
                continue;
            QString ch;
            line += (cellChars(cell, ch) > 0) ? ch : QStringLiteral(" ");
        }
        while (line.endsWith(QLatin1Char(' ')))
            line.chop(1);
        if (pos != s.y())
            out += QLatin1Char('\n');
        out += line;
    }
    return out;
}

void TerminalView::copySelection(bool toPrimary) {
    const QString text = selectionText();
    if (text.isEmpty())
        return;
    QApplication::clipboard()->setText(
        text, toPrimary ? QClipboard::Selection : QClipboard::Clipboard);
}

void TerminalView::paste(bool fromPrimary) {
    if (!m_pty)
        return;
    const QString text = QApplication::clipboard()->text(
        fromPrimary ? QClipboard::Selection : QClipboard::Clipboard);
    if (text.isEmpty())
        return;
    scrollToBottom();
    m_pty->write(text.toUtf8());
}

void TerminalView::mousePressEvent(QMouseEvent *ev) {
    if (ev->button() == Qt::MiddleButton) {
        paste(true);                        // primary selection
        return;
    }
    if (ev->button() == Qt::LeftButton) {
        setFocus();
        const QPoint cell = pixelToCell(ev->pos());
        if (ev->modifiers() & Qt::ControlModifier) {
            const QString url = urlAt(cell.y(), cell.x());
            if (!url.isEmpty()) {
                QDesktopServices::openUrl(QUrl(url));
                return;                 // ctrl-click opened a link; don't select
            }
        }
        m_selecting = true;
        m_selAnchor = m_selPoint = cell;
        m_hasSel = false;
        update();
    }
}

void TerminalView::mouseMoveEvent(QMouseEvent *ev) {
    if (!m_selecting)
        return;
    m_selPoint = pixelToCell(ev->pos());
    m_hasSel = (m_selPoint != m_selAnchor);
    update();
}

void TerminalView::mouseReleaseEvent(QMouseEvent *ev) {
    if (ev->button() != Qt::LeftButton)
        return;
    m_selecting = false;
    if (m_hasSel)
        copySelection(true);                // mirror to primary, X11-style
}

void TerminalView::keyPressEvent(QKeyEvent *ev) {
    if (!m_session)
        return;

    const Qt::KeyboardModifiers qm = ev->modifiers();

    // Clipboard + scroll bindings (Ctrl+Shift+C/V, Shift+PageUp/Down).
    if (qm.testFlag(Qt::ControlModifier) && qm.testFlag(Qt::ShiftModifier)) {
        if (ev->key() == Qt::Key_C) { copySelection(false); return; }
        if (ev->key() == Qt::Key_V) { paste(false); return; }
    }
    if (qm.testFlag(Qt::ShiftModifier)) {
        if (ev->key() == Qt::Key_PageUp) {
            setScrollOffset(m_scrollOffset + std::max(1, m_session->rows() - 1));
            return;
        }
        if (ev->key() == Qt::Key_PageDown) {
            setScrollOffset(m_scrollOffset - std::max(1, m_session->rows() - 1));
            return;
        }
    }

    // Any real input returns to the live view.
    scrollToBottom();

    VTermModifier mod = VTERM_MOD_NONE;
    if (qm & Qt::ShiftModifier)
        mod = static_cast<VTermModifier>(mod | VTERM_MOD_SHIFT);
    if (qm & Qt::AltModifier)
        mod = static_cast<VTermModifier>(mod | VTERM_MOD_ALT);
    if (qm & Qt::ControlModifier)
        mod = static_cast<VTermModifier>(mod | VTERM_MOD_CTRL);

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

    const QString text = ev->text();
    if (!text.isEmpty()) {
        const auto ucs = text.toUcs4();
        for (uint c : ucs)
            if (c >= 0x20)
                m_session->inputChar(c, VTERM_MOD_NONE);
    }
}
