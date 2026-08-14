#include "layershell.h"

#include <QWindow>

namespace helm {

void applyLayerShell(QWindow *win, LayerShellQt::Window::Layer layer,
                     LayerShellQt::Window::Anchors anchors, int exclusiveZone,
                     LayerShellQt::Window::KeyboardInteractivity keyboard,
                     const QMargins &margins) {
    if (!win)
        return;
    auto *ls = LayerShellQt::Window::get(win);
    if (!ls)
        return;
    ls->setLayer(layer);
    ls->setAnchors(anchors);
    ls->setExclusiveZone(exclusiveZone);
    ls->setKeyboardInteractivity(keyboard);
    ls->setMargins(margins);
}

} // namespace helm
