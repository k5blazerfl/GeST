#include "vtermsession.h"

#include "sixel.h"

#include <algorithm>

VTermSession::VTermSession(int rows, int cols, QObject *parent)
    : QObject(parent), m_rows(rows), m_cols(cols) {
    m_vt = vterm_new(rows, cols);
    vterm_set_utf8(m_vt, 1);
    vterm_output_set_callback(m_vt, &VTermSession::onOutput, this);

    m_screen = vterm_obtain_screen(m_vt);
    // Maintain the alternate screen buffer, so full-screen apps (ncurses TUIs)
    // that switch to it on entry restore the primary screen on exit — otherwise
    // the TUI's last frame lingers and the shell prompt prints over it.
    vterm_screen_enable_altscreen(m_screen, 1);

    static const VTermScreenCallbacks cb = {
        .damage      = &VTermSession::onDamage,
        .moverect    = nullptr,
        .movecursor  = &VTermSession::onMoveCursor,
        .settermprop = &VTermSession::onSetTermProp,
        .bell        = &VTermSession::onBell,
        .resize      = &VTermSession::onResize,
        .sb_pushline = &VTermSession::onPushline,
        .sb_popline  = &VTermSession::onPopline,
        .sb_clear    = &VTermSession::onSbClear,
    };
    vterm_screen_set_callbacks(m_screen, &cb, this);

    // Catch DCS sequences libvterm doesn't decode — notably sixel graphics.
    static const VTermStateFallbacks fb = {
        .control = nullptr,
        .csi     = nullptr,
        .osc     = nullptr,
        .dcs     = &VTermSession::onDcs,
        .apc     = nullptr,
        .pm      = nullptr,
        .sos     = nullptr,
    };
    vterm_screen_set_unrecognised_fallbacks(m_screen, &fb, this);

    // Light-on-dark defaults, matching the app-icon screen.
    VTermColor fg, bg;
    vterm_color_rgb(&fg, 0xe9, 0xee, 0xf6);
    vterm_color_rgb(&bg, 0x0e, 0x17, 0x28);
    vterm_screen_set_default_colors(m_screen, &fg, &bg);

    vterm_screen_reset(m_screen, /*hard=*/1);
}

VTermSession::~VTermSession() {
    if (m_vt)
        vterm_free(m_vt);        // frees the screen too
}

void VTermSession::writeInput(const QByteArray &bytes) {
    vterm_input_write(m_vt, bytes.constData(), static_cast<size_t>(bytes.size()));
    // A sixel image reserved text rows below it: advance the cursor now that the
    // parse is done (feeding LFs mid-parse would reenter the parser).
    if (m_pendingRows > 0) {
        const QByteArray lf(m_pendingRows, '\n');
        vterm_input_write(m_vt, lf.constData(), static_cast<size_t>(lf.size()));
        vterm_input_write(m_vt, "\r", 1);
        m_pendingRows = 0;
    }
    vterm_screen_flush_damage(m_screen);
}

void VTermSession::setSize(int rows, int cols) {
    if (rows <= 0 || cols <= 0 || (rows == m_rows && cols == m_cols))
        return;
    m_rows = rows;
    m_cols = cols;
    vterm_set_size(m_vt, rows, cols);
    vterm_screen_flush_damage(m_screen);
}

void VTermSession::inputChar(uint32_t c, VTermModifier mod) {
    vterm_keyboard_unichar(m_vt, c, mod);
}

void VTermSession::inputKey(VTermKey key, VTermModifier mod) {
    vterm_keyboard_key(m_vt, key, mod);
}

bool VTermSession::cell(int row, int col, VTermScreenCell &out) const {
    VTermPos p { row, col };
    return vterm_screen_get_cell(m_screen, p, &out) != 0;
}

bool VTermSession::scrollbackCell(int line, int col, VTermScreenCell &out) const {
    if (line < 0 || line >= static_cast<int>(m_scrollback.size()))
        return false;
    const std::vector<VTermScreenCell> &l = m_scrollback[static_cast<size_t>(line)];
    if (col < 0 || col >= static_cast<int>(l.size())) {
        out = VTermScreenCell {};
        out.width = 1;
        return true;                 // past the stored width — a blank cell
    }
    out = l[static_cast<size_t>(col)];
    return true;
}

QColor VTermSession::toColor(VTermColor col) const {
    if (!VTERM_COLOR_IS_RGB(&col))
        vterm_screen_convert_color_to_rgb(m_screen, &col);
    return QColor(col.rgb.red, col.rgb.green, col.rgb.blue);
}

void VTermSession::setDefaultColors(const QColor &fg, const QColor &bg) {
    m_defaultFg = fg;
    m_defaultBg = bg;
    VTermColor vf, vb;
    vterm_color_rgb(&vf, static_cast<uint8_t>(fg.red()),
                    static_cast<uint8_t>(fg.green()), static_cast<uint8_t>(fg.blue()));
    vterm_color_rgb(&vb, static_cast<uint8_t>(bg.red()),
                    static_cast<uint8_t>(bg.green()), static_cast<uint8_t>(bg.blue()));
    vterm_screen_set_default_colors(m_screen, &vf, &vb);
    emit damaged(QRect(0, 0, m_cols, m_rows));    // re-tint the whole surface
}

// --- libvterm callbacks -----------------------------------------------------

void VTermSession::onOutput(const char *s, size_t len, void *user) {
    auto *self = static_cast<VTermSession *>(user);
    emit self->outputReady(QByteArray(s, static_cast<int>(len)));
}

int VTermSession::onDamage(VTermRect r, void *user) {
    auto *self = static_cast<VTermSession *>(user);
    emit self->damaged(QRect(r.start_col, r.start_row,
                             r.end_col - r.start_col, r.end_row - r.start_row));
    return 1;
}

int VTermSession::onMoveCursor(VTermPos pos, VTermPos oldpos, int visible, void *user) {
    auto *self = static_cast<VTermSession *>(user);
    self->m_cursor = pos;
    self->m_cursorVisible = visible != 0;
    emit self->cursorMoved(QRect(oldpos.col, oldpos.row, 1, 1),
                           QRect(pos.col, pos.row, 1, 1));
    return 1;
}

int VTermSession::onSetTermProp(VTermProp prop, VTermValue *val, void *user) {
    auto *self = static_cast<VTermSession *>(user);
    switch (prop) {
    case VTERM_PROP_TITLE: {
        const VTermStringFragment f = val->string;
        if (f.initial)
            self->m_title.clear();
        self->m_title.append(f.str, static_cast<int>(f.len));
        if (f.final)
            emit self->titleChanged(QString::fromUtf8(self->m_title));
        break;
    }
    case VTERM_PROP_CURSORVISIBLE:
        self->m_cursorVisible = val->boolean != 0;
        emit self->cursorMoved(QRect(self->m_cursor.col, self->m_cursor.row, 1, 1),
                               QRect(self->m_cursor.col, self->m_cursor.row, 1, 1));
        break;
    default:
        break;
    }
    return 1;
}

int VTermSession::onBell(void *user) {
    emit static_cast<VTermSession *>(user)->bell();
    return 1;
}

int VTermSession::onResize(int rows, int cols, void *user) {
    auto *self = static_cast<VTermSession *>(user);
    self->m_rows = rows;
    self->m_cols = cols;
    return 1;
}

int VTermSession::onPushline(int cols, const VTermScreenCell *cells, void *user) {
    auto *self = static_cast<VTermSession *>(user);
    if (self->m_scrollbackMax <= 0)
        return 1;
    self->m_scrollback.emplace_back(cells, cells + cols);
    while (static_cast<int>(self->m_scrollback.size()) > self->m_scrollbackMax)
        self->m_scrollback.pop_front();
    emit self->lineScrolledOff();
    return 1;
}

int VTermSession::onPopline(int cols, VTermScreenCell *cells, void *user) {
    auto *self = static_cast<VTermSession *>(user);
    if (self->m_scrollback.empty())
        return 0;                    // nothing to restore
    const std::vector<VTermScreenCell> &line = self->m_scrollback.back();
    const int n = std::min(cols, static_cast<int>(line.size()));
    for (int i = 0; i < n; ++i)
        cells[i] = line[static_cast<size_t>(i)];
    for (int i = n; i < cols; ++i) {
        cells[i] = VTermScreenCell {};
        cells[i].width = 1;
    }
    self->m_scrollback.pop_back();
    return 1;
}

int VTermSession::onSbClear(void *user) {
    static_cast<VTermSession *>(user)->m_scrollback.clear();
    return 1;
}

int VTermSession::onDcs(const char *command, size_t commandlen,
                        VTermStringFragment frag, void *user) {
    auto *self = static_cast<VTermSession *>(user);
    // Sixel DCS ends its introducer with 'q' (e.g. "0;0;8q").
    const bool isSixel = commandlen > 0 && command[commandlen - 1] == 'q';

    if (frag.initial) {
        self->m_inSixel = isSixel;
        if (self->m_inSixel)
            self->m_sixelBuf.clear();
    }
    if (!self->m_inSixel)
        return 1;

    if (frag.len > 0)
        self->m_sixelBuf.append(frag.str, static_cast<int>(frag.len));

    if (frag.final) {
        self->m_inSixel = false;
        const QImage img = decodeSixel(self->m_sixelBuf);
        self->m_sixelBuf.clear();
        if (!img.isNull()) {
            const int absPos = self->scrollbackCount() + self->m_cursor.row;
            emit self->imageReceived(img, absPos, self->m_cursor.col);
            const int rows = (img.height() + self->m_cellHeight - 1) / self->m_cellHeight;
            self->m_pendingRows += std::max(1, rows);
        }
    }
    return 1;
}
