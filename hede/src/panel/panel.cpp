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

    auto *layout = new QHBoxLayout(this);
    layout->setContentsMargins(6, 2, 6, 2);
    layout->setSpacing(6);

    layout->addWidget(new LauncherButton(tr("≡ Apps"), resolveMenuCommand(), this));
    layout->addWidget(new TaskbarWidget(this), 1); // window list fills the middle

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
