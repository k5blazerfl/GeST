#pragma once

#include <QString>
#include <QStringList>
#include <QVector>

namespace helm {

// What an applet id places on the bar — an actual widget, or a flexible gap.
enum class AppletKind {
    Widget,  // launcher, taskbar, clock, tray, the status pills, …
    Stretch, // an expanding gap (`spacer`) — for a bar with no taskbar
};

// One entry in the panel's applet catalog: the token written to [panel] applets,
// a human label for the editor's add-drawer, its kind, and whether it belongs to
// the built-in default lineup.
struct AppletInfo {
    QString id;
    QString label;
    AppletKind kind = AppletKind::Widget;
    bool inDefault = true;
};

// The canonical registry of built-in applets, in default bar order (left→right).
// The single source of truth for "what applets exist" and for the default lineup
// an un-configured panel shows.
const QVector<AppletInfo> &appletCatalog();

// The default lineup: the ids of the catalog's default entries, in order.
QStringList defaultApplets();

// Look an applet up by id (`stretch` is accepted as an alias of `spacer`).
// Returns nullptr for an unknown id.
const AppletInfo *findApplet(const QString &id);

// Whether `id` names a known applet (a catalog entry or a recognised alias).
bool isKnownApplet(const QString &id);

} // namespace helm
