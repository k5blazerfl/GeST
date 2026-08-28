#include "agentlistener.h"

#include "controller.h"

extern "C" {
#include <glib-object.h>
#include <polkit/polkit.h>
}

#include <pwd.h>

// A minimal PolkitAgentListener subclass. polkit's own libpolkit-agent-1 handles
// the D-Bus AuthenticationAgent interface + registration; we only override the
// initiate vfunc to drive the Qt controller. (GObject boilerplate in C++.)
struct _HelmAgentListener {
    PolkitAgentListener parent_instance;
    AgentController *controller;
};
struct _HelmAgentListenerClass {
    PolkitAgentListenerClass parent_class;
};
typedef struct _HelmAgentListener HelmAgentListener;
typedef struct _HelmAgentListenerClass HelmAgentListenerClass;

G_DEFINE_TYPE(HelmAgentListener, helm_agent_listener, POLKIT_AGENT_TYPE_LISTENER)

static void helm_initiate_authentication(PolkitAgentListener *listener,
                                         const gchar *action_id, const gchar *message,
                                         const gchar *icon_name, PolkitDetails *details,
                                         const gchar *cookie, GList *identities,
                                         GCancellable *cancellable,
                                         GAsyncReadyCallback callback, gpointer user_data) {
    Q_UNUSED(action_id);
    Q_UNUSED(details);
    auto *self = reinterpret_cast<HelmAgentListener *>(listener);
    GTask *task = g_task_new(listener, cancellable, callback, user_data);

    QList<AuthIdentity> ids;
    for (GList *l = identities; l != nullptr; l = l->next) {
        auto *id = static_cast<PolkitIdentity *>(l->data);
        if (POLKIT_IS_UNIX_USER(id)) {
            const int uid = polkit_unix_user_get_uid(POLKIT_UNIX_USER(id));
            const struct passwd *pw = ::getpwuid(static_cast<uid_t>(uid));
            ids.append({uid, pw ? QString::fromUtf8(pw->pw_name) : QString::number(uid)});
        }
    }

    self->controller->begin(QString::fromUtf8(message ? message : ""),
                            QString::fromUtf8(icon_name ? icon_name : ""), ids,
                            QString::fromUtf8(cookie ? cookie : ""), task, cancellable);
}

static gboolean helm_initiate_authentication_finish(PolkitAgentListener *listener,
                                                    GAsyncResult *res, GError **error) {
    Q_UNUSED(listener);
    return g_task_propagate_boolean(G_TASK(res), error);
}

static void helm_agent_listener_class_init(HelmAgentListenerClass *klass) {
    PolkitAgentListenerClass *lk = POLKIT_AGENT_LISTENER_CLASS(klass);
    lk->initiate_authentication = helm_initiate_authentication;
    lk->initiate_authentication_finish = helm_initiate_authentication_finish;
}

static void helm_agent_listener_init(HelmAgentListener *self) {
    self->controller = nullptr;
}

PolkitAgentListener *helm_agent_listener_new(AgentController *controller) {
    auto *self = static_cast<HelmAgentListener *>(
        g_object_new(helm_agent_listener_get_type(), nullptr));
    self->controller = controller;
    return POLKIT_AGENT_LISTENER(self);
}
