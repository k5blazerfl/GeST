#include "helmdecoration.h"

#include "config.h"
#include "nineslice.h"
#include "world.h"

#include <QtWaylandClient/private/qwaylandwindow_p.h>

#include <QLinearGradient>
#include <QPainter>
#include <QWindow>

using QtWaylandClient::QWaylandInputDevice;

HelmDecoration::HelmDecoration() { loadWorld(); }

void HelmDecoration::loadWorld() {
    const helm::Config cfg;
    const helm::World w = helm::loadWorld(cfg.string(QStringLiteral("world/id"),
                                                     QStringLiteral("harbor")));
    if (w.frameTop > 0)
        m_top = w.frameTop;
    if (w.frameLeft > 0)
        m_border = w.frameLeft;

    // Accent precedence mirrors helm::effectiveAccent: explicit choice, else the
    // world, else Harbor teal.
    const QString explicitAccent = cfg.string(QStringLiteral("appearance/accent"));
    const QString accent = !explicitAccent.isEmpty()
                               ? explicitAccent
                               : (w.accent.isEmpty() ? QStringLiteral("#3aa6c4") : w.accent);
    m_accent = QColor(accent);
    if (!m_accent.isValid())
        m_accent = QColor(QStringLiteral("#3aa6c4"));

    const QString framePath = w.framePath();
    if (!framePath.isEmpty())
        m_frame = QImage(framePath);
}

QSize HelmDecoration::decoratedSize() const {
    return window() ? window()->frameGeometry().size() : QSize();
}

QMargins HelmDecoration::margins(MarginsType marginsType) const {
    if (marginsType == ShadowsOnly)
        return QMargins();
    return QMargins(m_border, m_top, m_border, m_border); // left, top, right, bottom
}

// Buttons sit at the top-right of the titlebar, each an m_top-tall square,
// ordered minimize / maximize / close (left → right).
QRectF HelmDecoration::closeButtonRect() const {
    const qreal w = decoratedSize().width();
    return QRectF(w - m_top, 0, m_top, m_top);
}
QRectF HelmDecoration::maximizeButtonRect() const {
    const qreal w = decoratedSize().width();
    return QRectF(w - 2 * m_top, 0, m_top, m_top);
}
QRectF HelmDecoration::minimizeButtonRect() const {
    const qreal w = decoratedSize().width();
    return QRectF(w - 3 * m_top, 0, m_top, m_top);
}

namespace {

// Draw an edgeless glyph button. `hoverClose` tints the close button red.
void drawButton(QPainter &p, const QRectF &r, const QString &glyph, bool hoverClose) {
    if (hoverClose)
        p.fillRect(r, QColor(232, 74, 74, 210)); // close hover → red chip
    p.save();
    p.setPen(QPen(QColor(255, 255, 255), 1.4));
    const QPointF c = r.center();
    const qreal s = 4.5;
    if (glyph == QLatin1String("x")) {
        p.drawLine(QPointF(c.x() - s, c.y() - s), QPointF(c.x() + s, c.y() + s));
        p.drawLine(QPointF(c.x() - s, c.y() + s), QPointF(c.x() + s, c.y() - s));
    } else if (glyph == QLatin1String("[]")) {
        p.setBrush(Qt::NoBrush);
        p.drawRect(QRectF(c.x() - s, c.y() - s, 2 * s, 2 * s));
    } else { // "-"
        p.drawLine(QPointF(c.x() - s, c.y() + s), QPointF(c.x() + s, c.y() + s));
    }
    p.restore();
}

} // namespace

void HelmDecoration::paint(QPaintDevice *device) {
    const QRect full(QPoint(0, 0), decoratedSize());
    if (full.isEmpty())
        return;

    QPainter p(device);
    // Clear the whole decoration buffer to transparent; the centre stays clear so
    // the app content (a separate subsurface) shows through.
    p.setCompositionMode(QPainter::CompositionMode_Source);
    p.fillRect(full, Qt::transparent);
    p.setCompositionMode(QPainter::CompositionMode_SourceOver);
    p.setRenderHints(QPainter::Antialiasing | QPainter::SmoothPixmapTransform);

    if (!m_frame.isNull()) {
        const QMargins insets(m_border, m_top, m_border, m_border);
        for (const helm::SliceRect &s : helm::nineSliceBorder(m_frame.size(), insets, full))
            p.drawImage(s.dst, m_frame, s.src);
    } else {
        // No frame art → an accent gradient titlebar + accent borders (mirrors the
        // labwc themerc fallback).
        QLinearGradient g(0, 0, 0, m_top);
        g.setColorAt(0, m_accent);
        g.setColorAt(1, m_accent.darker(122));
        p.fillRect(QRect(0, 0, full.width(), m_top), g);
        p.fillRect(QRect(0, 0, m_border, full.height()), m_accent);
        p.fillRect(QRect(full.width() - m_border, 0, m_border, full.height()), m_accent);
        p.fillRect(QRect(0, full.height() - m_border, full.width(), m_border), m_accent);
    }

    // Title text.
    p.setPen(QColor(255, 255, 255));
    QFont f = p.font();
    f.setBold(true);
    p.setFont(f);
    const int titleRight = minimizeButtonRect().left() - 8;
    p.drawText(QRect(12, 0, titleRight - 12, m_top), Qt::AlignVCenter | Qt::AlignLeft,
               window() ? window()->title() : QString());

    // Edgeless buttons.
    drawButton(p, minimizeButtonRect(), QStringLiteral("-"), false);
    drawButton(p, maximizeButtonRect(), QStringLiteral("[]"), false);
    drawButton(p, closeButtonRect(), QStringLiteral("x"), m_hoverClose);
}

Qt::Edges HelmDecoration::resizeEdges(const QPointF &local) const {
    const QSize sz = decoratedSize();
    Qt::Edges e;
    if (local.x() <= m_border)
        e |= Qt::LeftEdge;
    else if (local.x() >= sz.width() - m_border)
        e |= Qt::RightEdge;
    if (local.y() >= sz.height() - m_border)
        e |= Qt::BottomEdge;
    // Top-edge resize is omitted — the titlebar owns the top.
    return e;
}

void HelmDecoration::toggleMaximize() {
    if (!window())
        return;
    const Qt::WindowStates st = window()->windowStates();
    if (st & Qt::WindowMaximized)
        window()->setWindowStates(st & ~Qt::WindowMaximized);
    else
        window()->setWindowStates(st | Qt::WindowMaximized);
}

bool HelmDecoration::handleMouse(QWaylandInputDevice *inputDevice, const QPointF &local,
                                 const QPointF &global, Qt::MouseButtons b,
                                 Qt::KeyboardModifiers mods) {
    Q_UNUSED(global);
    Q_UNUSED(mods);

    const bool overClose = closeButtonRect().contains(local);
    if (overClose != m_hoverClose) {
        m_hoverClose = overClose;
        update();
    }

    bool handled = false;
    if (isLeftClicked(b)) {
        if (closeButtonRect().contains(local)) {
            if (window())
                window()->close();
            handled = true;
        } else if (minimizeButtonRect().contains(local)) {
            if (window())
                window()->setWindowStates(window()->windowStates() | Qt::WindowMinimized);
            handled = true;
        } else if (maximizeButtonRect().contains(local)) {
            toggleMaximize();
            handled = true;
        } else if (const Qt::Edges e = resizeEdges(local)) {
            startResize(inputDevice, e, b);
            handled = true;
        } else if (local.y() <= m_top) {
            startMove(inputDevice, b);
            handled = true;
        }
    } else if (b == Qt::RightButton && local.y() <= m_top) {
        showWindowMenu(inputDevice);
        handled = true;
    }

    setMouseButtons(b);
    return handled;
}

bool HelmDecoration::handleTouch(QWaylandInputDevice *inputDevice, const QPointF &local,
                                 const QPointF &global, QEventPoint::State state,
                                 Qt::KeyboardModifiers mods) {
    Q_UNUSED(global);
    Q_UNUSED(mods);
    if (state != QEventPoint::Pressed)
        return false;
    if (closeButtonRect().contains(local)) {
        if (window())
            window()->close();
        return true;
    }
    if (local.y() <= m_top) {
        startMove(inputDevice, Qt::LeftButton);
        return true;
    }
    return false;
}
