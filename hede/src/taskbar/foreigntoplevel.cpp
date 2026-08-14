#include "foreigntoplevel.h"

#include <QGuiApplication>
#include <QtGui/qguiapplication_platform.h>

#include <wayland-client.h>

namespace helm {

static QString handleKey(::zwlr_foreign_toplevel_handle_v1 *h) {
    return QString::number(reinterpret_cast<quintptr>(h));
}

static ::wl_seat *currentSeat() {
    if (auto *wl = qGuiApp->nativeInterface<QNativeInterface::QWaylandApplication>())
        return wl->seat();
    return nullptr;
}

// ---------------- manager ----------------

ForeignToplevelManager::ForeignToplevelManager()
    : QWaylandClientExtensionTemplate<ForeignToplevelManager>(3) {}

void ForeignToplevelManager::zwlr_foreign_toplevel_manager_v1_toplevel(
    ::zwlr_foreign_toplevel_handle_v1 *toplevel) {
    auto *h = new ForeignToplevelHandle(toplevel, this);
    m_handles.insert(h->key(), h);
}

void ForeignToplevelManager::activate(const QString &key) {
    if (auto *h = m_handles.value(key))
        if (auto *seat = currentSeat())
            h->activate(seat);
}

void ForeignToplevelManager::toggleMinimize(const QString &key) {
    if (auto *h = m_handles.value(key)) {
        if (h->minimized())
            h->unset_minimized();
        else
            h->set_minimized();
    }
}

void ForeignToplevelManager::close(const QString &key) {
    if (auto *h = m_handles.value(key))
        h->close();
}

// ---------------- handle ----------------

ForeignToplevelHandle::ForeignToplevelHandle(::zwlr_foreign_toplevel_handle_v1 *handle,
                                             ForeignToplevelManager *manager)
    : QtWayland::zwlr_foreign_toplevel_handle_v1(handle), m_manager(manager),
      m_key(handleKey(handle)) {}

void ForeignToplevelHandle::zwlr_foreign_toplevel_handle_v1_title(const QString &title) {
    m_title = title;
}

void ForeignToplevelHandle::zwlr_foreign_toplevel_handle_v1_app_id(const QString &appId) {
    m_appId = appId;
}

void ForeignToplevelHandle::zwlr_foreign_toplevel_handle_v1_state(wl_array *state) {
    m_activated = false;
    m_minimized = false;
    const auto *data = static_cast<const uint32_t *>(state->data);
    const size_t n = state->size / sizeof(uint32_t);
    for (size_t i = 0; i < n; ++i) {
        if (data[i] == QtWayland::zwlr_foreign_toplevel_handle_v1::state_activated)
            m_activated = true;
        else if (data[i] == QtWayland::zwlr_foreign_toplevel_handle_v1::state_minimized)
            m_minimized = true;
    }
}

void ForeignToplevelHandle::zwlr_foreign_toplevel_handle_v1_done() {
    Toplevel t;
    t.key = m_key;
    t.title = m_title;
    t.appId = m_appId;
    t.activated = m_activated;
    t.minimized = m_minimized;
    emit m_manager->toplevelChanged(t);
}

void ForeignToplevelHandle::zwlr_foreign_toplevel_handle_v1_closed() {
    m_manager->m_handles.remove(m_key);
    emit m_manager->toplevelClosed(m_key);
    destroy();
    deleteLater();
}

} // namespace helm
