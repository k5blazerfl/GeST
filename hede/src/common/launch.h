#pragma once

#include <QString>
#include <QStringList>

namespace helm {

// Start a detached GUI application the HeDE way.
//
// Forces server-side decorations (QT_WAYLAND_DISABLE_WINDOWDECORATION=1) in the
// child's environment so a Qt app launched straight from the shell — the Start
// menu, a panel button, the update pill — comes up with a labwc titlebar instead
// of frameless. Qt's client-side decoration doesn't render under labwc, so we
// drop CSD and let the compositor decorate. Terminal-launched apps already
// inherit this from the session; routing every shell launch through here
// guarantees it for menu/panel-launched ones too.
//
// Returns true if the process was started.
bool launchDetached(const QString &program, const QStringList &arguments = {});

} // namespace helm
