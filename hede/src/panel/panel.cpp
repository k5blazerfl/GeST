#include "panel.h"

#include "clock.h"
#include "config.h"
#include "launcherbutton.h"
#include "taskbarwidget.h"
#include "traywidget.h"

#include "batterypill.h"
#include "coreclient.h"
#include "networkpill.h"
#include "updatepill.h"

#include "brightness.h"
#include "dndtoggle.h"
#include "volume.h"

#include "mpris.h"

#include <QCoreApplication>
#include <QFileInfo>
#include <QHBoxLayout>

namespace helm {

// Resolve helm-menu: prefer a sibling of this binary (dev / build tree), then
// the menu/ build subdir, else fall back to $PATH.
static QString resolveMenuCommand() {
    const QString here = QCoreApplication::applicationDirPath();
    const QStringList candidates = {here + QStringLiteral("/helm-menu"),
                                    here + QStringLiteral("/../menu/helm-menu")};
    for (const QString &c : candidates)
        if (QFileInfo::exists(c))
            return QFileInfo(c).absoluteFilePath();
    return QStringLiteral("helm-menu");
}

Panel::Panel(QWidget *parent) : QWidget(parent) {
    const Config cfg;
    setFixedHeight(cfg.panelHeight());

    // The glass bar: objectName drives the #HelmBar QSS (see helm::styleSheet);
    // styled + translucent so the world-navy tint composites over the wallpaper.
    setObjectName(QStringLiteral("HelmBar"));
    setAttribute(Qt::WA_StyledBackground, true);
    setAttribute(Qt::WA_TranslucentBackground, true);

    auto *layout = new QHBoxLayout(this);
    layout->setContentsMargins(8, 0, 8, 0); // tokens.spacing[1] sides, flush vertically
    layout->setSpacing(6);

    // The status pills share one seam client (GeST reads); construct it lazily so
    // a config that drops every pill pays nothing for it.
    CoreClient *core = nullptr;
    auto sharedCore = [&]() -> CoreClient * {
        if (!core)
            core = new CoreClient(this);
        return core;
    };

    // Build the bar from the ordered [panel] applets list (Barnacle's surface).
    // An un-configured panel gets the built-in default lineup, so this is a pure
    // refactor of the previous hard-coded order — same widgets, same sequence.
    for (const QString &name : cfg.panelApplets()) {
        if (name == QLatin1String("launcher")) {
            // The ⎈ Start tile — Helm mark + label (label keeps it discoverable
            // if the glyph is missing from the installed font); #HelmStart styles it.
            auto *start =
                new LauncherButton(QString::fromUtf8("⎈  Apps"), resolveMenuCommand(), this);
            start->setObjectName(QStringLiteral("HelmStart"));
            layout->addWidget(start);
        } else if (name == QLatin1String("taskbar")) {
            layout->addWidget(new TaskbarWidget(this), 1); // window list fills the middle
        } else if (name == QLatin1String("spacer") || name == QLatin1String("stretch")) {
            layout->addStretch(1); // explicit flexible gap (bar with no taskbar)
        } else if (name == QLatin1String("mpris")) {
            layout->addWidget(new MprisApplet(this)); // media controls (MPRIS)
        } else if (name == QLatin1String("update")) {
            layout->addWidget(new UpdatePill(sharedCore(), this)); // "N updates"
        } else if (name == QLatin1String("network")) {
            layout->addWidget(new NetworkPill(sharedCore(), this)); // wired / wifi / offline
        } else if (name == QLatin1String("battery")) {
            layout->addWidget(new BatteryPill(sharedCore(), this)); // NN%
        } else if (name == QLatin1String("brightness")) {
            layout->addWidget(new BrightnessApplet(this)); // brightnessctl
        } else if (name == QLatin1String("volume")) {
            layout->addWidget(new VolumeApplet(this)); // wpctl (PipeWire)
        } else if (name == QLatin1String("dnd")) {
            layout->addWidget(new DndToggle(this)); // do-not-disturb (helm-notifyd)
        } else if (name == QLatin1String("tray")) {
            layout->addWidget(new TrayWidget(this)); // system tray
        } else if (name == QLatin1String("clock")) {
            layout->addWidget(new Clock(this));
        } else {
            qWarning("helm-panel: unknown applet in [panel] applets: %s",
                     qUtf8Printable(name));
        }
    }
}

} // namespace helm
