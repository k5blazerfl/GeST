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

    // The ⎈ Start tile — Helm mark + label (label keeps it discoverable if the
    // glyph is missing from the installed font); #HelmStart styles it.
    auto *start = new LauncherButton(QString::fromUtf8("⎈  Apps"), resolveMenuCommand(), this);
    start->setObjectName(QStringLiteral("HelmStart"));
    layout->addWidget(start);
    layout->addWidget(new TaskbarWidget(this), 1); // window list fills the middle

    layout->addWidget(new MprisApplet(this)); // media controls (MPRIS)

    // Quick-settings indicators, all sharing one seam client (GeST reads).
    auto *core = new CoreClient(this);
    layout->addWidget(new UpdatePill(core, this));  // "N updates"
    layout->addWidget(new NetworkPill(core, this)); // wired / wifi / offline
    layout->addWidget(new BatteryPill(core, this)); // NN%

    // Direct-to-system quick settings (scroll to adjust).
    layout->addWidget(new BrightnessApplet(this)); // brightnessctl
    layout->addWidget(new VolumeApplet(this));     // wpctl (PipeWire)
    layout->addWidget(new DndToggle(this));        // do-not-disturb (helm-notifyd)

    layout->addWidget(new TrayWidget(this)); // system tray
    layout->addWidget(new Clock(this));
}

} // namespace helm
