#pragma once

#include <LayerShellQt/Window>

#include <QMargins>

class QWindow;

namespace helm {

// Build an Anchors flag set from edges (the enum has no operator|).
inline LayerShellQt::Window::Anchors edges(bool top, bool bottom, bool left, bool right) {
    LayerShellQt::Window::Anchors a;
    if (top)
        a |= LayerShellQt::Window::AnchorTop;
    if (bottom)
        a |= LayerShellQt::Window::AnchorBottom;
    if (left)
        a |= LayerShellQt::Window::AnchorLeft;
    if (right)
        a |= LayerShellQt::Window::AnchorRight;
    return a;
}

// Promote a realised QWindow to a wlr-layer-shell surface. Call after winId().
void applyLayerShell(QWindow *win, LayerShellQt::Window::Layer layer,
                     LayerShellQt::Window::Anchors anchors, int exclusiveZone,
                     LayerShellQt::Window::KeyboardInteractivity keyboard,
                     const QMargins &margins = {});

} // namespace helm
