#include "panel.h"

#include "clock.h"
#include "config.h"
#include "launcherbutton.h"
#include "layout.h"
#include "palette.h"
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

#include <QBoxLayout>
#include <QCoreApplication>
#include <QFileInfo>
#include <QFileSystemWatcher>
#include <QLayoutItem>
#include <QTimer>

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
    // The glass bar: objectName drives the #HelmBar QSS (see helm::styleSheet);
    // styled + translucent so the world-navy tint composites over the wallpaper.
    setObjectName(QStringLiteral("HelmBar"));
    setAttribute(Qt::WA_StyledBackground, true);
    setAttribute(Qt::WA_TranslucentBackground, true);

    m_layout = new QBoxLayout(QBoxLayout::LeftToRight, this);
    m_layout->setSpacing(6);

    applyGeometry(); // orientation + thickness from [panel] edge/height
    buildApplets();
}

// Orient the bar for its edge and reserve its thickness. bottom/top run
// horizontal (thickness = height); left/right run vertical (thickness = width).
// [panel] height is the bar's thickness in either orientation.
void Panel::applyGeometry() {
    const Config cfg;
    const int thickness = cfg.panelHeight();
    const QString edge = PanelLayout::readEdge(cfg.path());
    const bool vertical = (edge == QLatin1String("left") || edge == QLatin1String("right"));

    m_layout->setDirection(vertical ? QBoxLayout::TopToBottom : QBoxLayout::LeftToRight);
    if (vertical) {
        m_layout->setContentsMargins(0, 8, 0, 8); // pad the ends, flush at the sides
        setMinimumHeight(0);
        setMaximumHeight(QWIDGETSIZE_MAX); // the compositor stretches us full-height
        setFixedWidth(thickness);
    } else {
        m_layout->setContentsMargins(8, 0, 8, 0);
        setMinimumWidth(0);
        setMaximumWidth(QWIDGETSIZE_MAX); // ...or full-width
        setFixedHeight(thickness);
    }
}

void Panel::buildApplets() {
    const Config cfg;

    // The status pills share one seam client (GeST reads); construct it lazily so
    // a config that drops every pill pays nothing for it.
    CoreClient *core = nullptr;
    auto sharedCore = [&]() -> CoreClient * {
        if (!core)
            core = new CoreClient(this);
        return core;
    };

    // Add a built applet and — because reload() runs after the bar is already
    // shown — make it visible now (a no-op cost while the panel is still hidden
    // during construction).
    auto add = [&](QWidget *w, int stretch = 0) {
        m_layout->addWidget(w, stretch);
        w->show();
    };

    // Build the bar from the ordered [panel] applets list (Barnacle's surface),
    // read through the shared engine so the bar and the editor never disagree.
    // An un-configured panel gets the built-in default lineup.
    for (const QString &name : PanelLayout::read(cfg.path())) {
        if (name == QLatin1String("launcher")) {
            // The ⎈ Start tile — Helm mark + label (label keeps it discoverable
            // if the glyph is missing from the installed font); #HelmStart styles it.
            auto *start =
                new LauncherButton(QString::fromUtf8("⎈  Apps"), resolveMenuCommand(), this);
            start->setObjectName(QStringLiteral("HelmStart"));
            add(start);
        } else if (name == QLatin1String("taskbar")) {
            add(new TaskbarWidget(this), 1); // window list fills the middle
        } else if (name == QLatin1String("spacer") || name == QLatin1String("stretch")) {
            m_layout->addStretch(1); // explicit flexible gap (bar with no taskbar)
        } else if (name == QLatin1String("mpris")) {
            add(new MprisApplet(this)); // media controls (MPRIS)
        } else if (name == QLatin1String("update")) {
            add(new UpdatePill(sharedCore(), this)); // "N updates"
        } else if (name == QLatin1String("network")) {
            add(new NetworkPill(sharedCore(), this)); // wired / wifi / offline
        } else if (name == QLatin1String("battery")) {
            add(new BatteryPill(sharedCore(), this)); // NN%
        } else if (name == QLatin1String("brightness")) {
            add(new BrightnessApplet(this)); // brightnessctl
        } else if (name == QLatin1String("volume")) {
            add(new VolumeApplet(this)); // wpctl (PipeWire)
        } else if (name == QLatin1String("dnd")) {
            add(new DndToggle(this)); // do-not-disturb (helm-notifyd)
        } else if (name == QLatin1String("tray")) {
            add(new TrayWidget(this)); // system tray
        } else if (name == QLatin1String("clock")) {
            add(new Clock(this));
        } else {
            qWarning("helm-panel: unknown applet in [panel] applets: %s", qUtf8Printable(name));
        }
    }
}

void Panel::reload() {
    // Tear down the current applets (and any stretch items), keeping the layout.
    while (QLayoutItem *item = m_layout->takeAt(0)) {
        if (QWidget *w = item->widget())
            w->deleteLater(); // children of `this`; defer so we don't delete mid-signal
        delete item;          // frees the layout item / spacer wrapper
    }

    applyGeometry(); // edge may have flipped orientation, or height changed
    buildApplets();
    Q_EMIT reloaded(); // owner re-anchors the surface (edge + thickness)
}

void Panel::watchConfig() {
    const QString path = Config().path();

    auto *watcher = new QFileSystemWatcher(this);
    // Watch the directory too: QSettings rewrites via a temp file + rename, which
    // drops the per-file watch, so we re-arm on every signal (as watchAppearance).
    watcher->addPath(QFileInfo(path).absolutePath());
    if (QFileInfo::exists(path))
        watcher->addPath(path);

    // Coalesce the burst a single save emits (temp-rename fires both directory-
    // and file-changed) into one rebuild, so the bar doesn't flicker twice.
    auto *debounce = new QTimer(this);
    debounce->setSingleShot(true);
    debounce->setInterval(50);
    connect(debounce, &QTimer::timeout, this, &Panel::reload);

    auto onChange = [this, watcher, path, debounce]() {
        if (!watcher->files().contains(path) && QFileInfo::exists(path))
            watcher->addPath(path); // re-arm after an atomic rewrite
        debounce->start();
    };
    connect(watcher, &QFileSystemWatcher::fileChanged, this, onChange);
    connect(watcher, &QFileSystemWatcher::directoryChanged, this, onChange);
}

void Panel::paintEvent(QPaintEvent *) { paintStyledSurface(this); }

} // namespace helm
