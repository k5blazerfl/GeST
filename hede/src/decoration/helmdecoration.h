#pragma once

#include <QtWaylandClient/private/qwaylandabstractdecoration_p.h>

#include <QColor>
#include <QImage>
#include <QRectF>

// HelmDecoration — HeDE's client-side window decoration. Draws the active world's
// nine-patch frame (decoration_art/frame.png) as a painterly titlebar + thin
// accent borders, with edgeless min/max/close buttons. Falls back to an
// accent gradient when the world ships no frame (e.g. Harbor before art lands).
//
// This is the path to true painterly frames that labwc's server-side decorations
// can't provide (Solid/Gradient titlebars only). Opt-in via HELM_CSD=1 in the
// session until QEMU-verified; see docs/design/hede-theme.md.
class HelmDecoration : public QtWaylandClient::QWaylandAbstractDecoration {
    Q_OBJECT
public:
    HelmDecoration();

    QMargins margins(MarginsType marginsType = Full) const override;
    bool handleMouse(QtWaylandClient::QWaylandInputDevice *inputDevice, const QPointF &local,
                     const QPointF &global, Qt::MouseButtons b,
                     Qt::KeyboardModifiers mods) override;
    bool handleTouch(QtWaylandClient::QWaylandInputDevice *inputDevice, const QPointF &local,
                     const QPointF &global, QEventPoint::State state,
                     Qt::KeyboardModifiers mods) override;

protected:
    void paint(QPaintDevice *device) override;

private:
    void loadWorld();
    QSize decoratedSize() const;
    QRectF closeButtonRect() const;
    QRectF maximizeButtonRect() const;
    QRectF minimizeButtonRect() const;
    Qt::Edges resizeEdges(const QPointF &local) const;
    void toggleMaximize();

    QImage m_frame;  // nine-patch frame; null → gradient fallback
    QColor m_accent; // world / explicit accent
    int m_top = 40;  // titlebar height
    int m_border = 8;
    bool m_hoverClose = false;
};
