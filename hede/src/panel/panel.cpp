#include "panel.h"

#include "clock.h"
#include "config.h"
#include "launcherbutton.h"

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
    layout->addStretch(1); // window list goes here next
    layout->addWidget(new Clock(this));
}

} // namespace helm
