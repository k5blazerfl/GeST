#include "catalog.h"

namespace helm {

const QVector<AppletInfo> &appletCatalog() {
    // Order here IS the default bar order (panel.cpp's dispatch must recognise
    // every id whose inDefault is true). `spacer` is offered by the editor but
    // not part of the default lineup — `taskbar` provides the fill by default.
    static const QVector<AppletInfo> kCatalog = {
        {QStringLiteral("launcher"), QStringLiteral("Start / Apps"), AppletKind::Widget, true},
        {QStringLiteral("taskbar"), QStringLiteral("Window list"), AppletKind::Widget, true},
        {QStringLiteral("mpris"), QStringLiteral("Media controls"), AppletKind::Widget, true},
        {QStringLiteral("update"), QStringLiteral("Updates"), AppletKind::Widget, true},
        {QStringLiteral("network"), QStringLiteral("Network"), AppletKind::Widget, true},
        {QStringLiteral("battery"), QStringLiteral("Battery"), AppletKind::Widget, true},
        {QStringLiteral("brightness"), QStringLiteral("Brightness"), AppletKind::Widget, true},
        {QStringLiteral("volume"), QStringLiteral("Volume"), AppletKind::Widget, true},
        {QStringLiteral("dnd"), QStringLiteral("Do Not Disturb"), AppletKind::Widget, true},
        {QStringLiteral("tray"), QStringLiteral("System tray"), AppletKind::Widget, true},
        {QStringLiteral("clock"), QStringLiteral("Clock"), AppletKind::Widget, true},
        {QStringLiteral("spacer"), QStringLiteral("Flexible space"), AppletKind::Stretch, false},
    };
    return kCatalog;
}

QStringList defaultApplets() {
    QStringList out;
    for (const AppletInfo &a : appletCatalog())
        if (a.inDefault)
            out.append(a.id);
    return out;
}

const AppletInfo *findApplet(const QString &id) {
    // `stretch` is a recognised synonym for the `spacer` gap (panel.cpp accepts
    // both), but the catalog carries a single canonical card.
    const QString key = (id == QLatin1String("stretch")) ? QStringLiteral("spacer") : id;
    for (const AppletInfo &a : appletCatalog())
        if (a.id == key)
            return &a;
    return nullptr;
}

bool isKnownApplet(const QString &id) { return findApplet(id) != nullptr; }

} // namespace helm
