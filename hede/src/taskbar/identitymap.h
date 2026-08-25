#pragma once

#include <QHash>
#include <QString>

namespace helm {

// Resolved taskbar identity for a foreign window: the icon theme-name and
// display name taken from the app's synthesized .desktop. `found` is false when
// the window's app-id isn't in the Customs identity map (a plain native app),
// in which case the taskbar keeps its text-only fallback.
struct WindowIdentity {
    bool found = false;
    QString iconName; // .desktop Icon= (theme name or path)
    QString name;     // .desktop Name=
};

// Reads the Customs identity map that Gangway/Drydock write
// (~/.local/share/hede/customs/identity.json) and resolves a
// wlr-foreign-toplevel app_id back to its synthesized .desktop's icon+name, so
// a remote/Wine window shows a real identity instead of a "freerdp"/"wine" blob.
//
// The GeST side is the source of truth (gest/core/customs/identity_store.py);
// this is the read half the design doc (docs/design/gangway-phase5-scope.md,
// item C) called out as the one missing piece. Pure of Wayland; file-backed and
// reloadable so newly-installed launchers are picked up without a restart.
class IdentityResolver {
  public:
    IdentityResolver();

    // (Re)read identity.json. Safe to call repeatedly; a missing or corrupt file
    // yields an empty map (same graceful contract as identity_store.load). Does
    // not drop the successful-lookup memo, so this stays cheap per rebuild.
    void reload();

    // Resolve a window's app_id/WM_CLASS to its .desktop identity, or a
    // not-found result. Xwayland (Wine/Proton) surfaces present their WM_CLASS
    // as the Wayland app_id, so there is a single key to match.
    WindowIdentity resolve(const QString &appId) const;

    // The identity map path: GenericDataLocation + /hede/customs/identity.json,
    // matching gest/core/customs/identity_store.py::default_path().
    static QString identityPath();

    // Normalize a key to match the Python writer (identity.py::normalize): trim,
    // lowercase, take the instance before a NUL (X11 WM_CLASS), keep dots intact
    // (reverse-DNS Wayland app-ids like org.freerdp.client use them).
    static QString normalizeKey(const QString &key);

  private:
    // Locate <desktop_id>.desktop across the XDG application dirs and read its
    // icon+name. Parses by id (not scanDesktopEntries) so NoDisplay handler
    // entries — e.g. Gangway's gangway-rdp-handler — still resolve.
    WindowIdentity entryForDesktopId(const QString &desktopId) const;

    QHash<QString, QString> m_byKey;                // normalized app_id → desktop_id
    mutable QHash<QString, WindowIdentity> m_cache; // desktop_id → resolved (memo, found only)
};

} // namespace helm
