#include "panel.h"

#include "clock.h"
#include "config.h"
#include "launcherbutton.h"

#include <QHBoxLayout>

namespace helm {

Panel::Panel(QWidget *parent) : QWidget(parent) {
    const Config cfg;
    setFixedHeight(cfg.panelHeight());

    auto *layout = new QHBoxLayout(this);
    layout->setContentsMargins(6, 2, 6, 2);
    layout->setSpacing(6);

    layout->addWidget(new LauncherButton(tr("Terminal"), cfg.terminalCommand(), this));
    layout->addStretch(1); // window list goes here in Phase 1
    layout->addWidget(new Clock(this));
}

} // namespace helm
