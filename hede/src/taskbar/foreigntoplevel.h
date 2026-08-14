#pragma once

#include <QHash>
#include <QObject>
#include <QWaylandClientExtensionTemplate>

#include "qwayland-wlr-foreign-toplevel-management-unstable-v1.h"

#include "toplevelmodel.h"

struct wl_array;

namespace helm {

class ForeignToplevelHandle;

// Binds the wlr-foreign-toplevel-management global and tracks open windows.
// Feeds Toplevel updates out as signals; offers per-window actions by key.
class ForeignToplevelManager : public QWaylandClientExtensionTemplate<ForeignToplevelManager>,
                               public QtWayland::zwlr_foreign_toplevel_manager_v1 {
    Q_OBJECT
  public:
    ForeignToplevelManager();

    void activate(const QString &key);
    void toggleMinimize(const QString &key);
    void close(const QString &key);

  signals:
    void toplevelChanged(const helm::Toplevel &t);
    void toplevelClosed(const QString &key);

  protected:
    void
    zwlr_foreign_toplevel_manager_v1_toplevel(::zwlr_foreign_toplevel_handle_v1 *toplevel) override;

  private:
    friend class ForeignToplevelHandle;
    QHash<QString, ForeignToplevelHandle *> m_handles;
};

// One open window. Accumulates title/app-id/state and commits on `done`.
class ForeignToplevelHandle : public QObject, public QtWayland::zwlr_foreign_toplevel_handle_v1 {
    Q_OBJECT
  public:
    ForeignToplevelHandle(::zwlr_foreign_toplevel_handle_v1 *handle,
                          ForeignToplevelManager *manager);
    QString key() const { return m_key; }
    bool minimized() const { return m_minimized; }

  protected:
    void zwlr_foreign_toplevel_handle_v1_title(const QString &title) override;
    void zwlr_foreign_toplevel_handle_v1_app_id(const QString &appId) override;
    void zwlr_foreign_toplevel_handle_v1_state(wl_array *state) override;
    void zwlr_foreign_toplevel_handle_v1_done() override;
    void zwlr_foreign_toplevel_handle_v1_closed() override;

  private:
    ForeignToplevelManager *m_manager;
    QString m_key;
    QString m_title;
    QString m_appId;
    bool m_activated = false;
    bool m_minimized = false;
};

} // namespace helm
