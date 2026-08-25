#pragma once

#include <QString>
#include <QStringList>

namespace helm {

// Start a detached GUI application the HeDE way.
//
// Sanitises the child's environment so a Qt app launched straight from the shell
// — the Start menu, a panel button, the update pill — behaves as a normal window:
//   * removes QT_WAYLAND_SHELL_INTEGRATION (the shell sets it to `layer-shell` for
//     its own surface; inherited, it makes children frameless always-on-top layer
//     surfaces — e.g. an unclosable fullscreen Control Center), so children get
//     the default xdg-toplevel integration labwc can manage; and
//   * sets QT_WAYLAND_DISABLE_WINDOWDECORATION=1 so labwc server-side-decorates it
//     (Qt's client-side decoration doesn't render under labwc → frameless).
// Terminal-launched apps already inherit a clean session env; routing every shell
// launch through here guarantees the same for menu/panel-launched ones.
//
// Returns true if the process was started.
bool launchDetached(const QString &program, const QStringList &arguments = {});

} // namespace helm
