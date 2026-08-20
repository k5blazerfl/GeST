#include "helmdecoration.h"

#include <QtWaylandClient/private/qwaylanddecorationplugin_p.h>

// The plugin factory: registered under the key "helm", selected with
// QT_WAYLAND_DECORATION=helm.
class HelmDecorationPlugin : public QtWaylandClient::QWaylandDecorationPlugin {
    Q_OBJECT
    Q_PLUGIN_METADATA(IID QWaylandDecorationFactoryInterface_iid FILE "helm.json")
public:
    QtWaylandClient::QWaylandAbstractDecoration *create(const QString &key,
                                                        const QStringList &paramList) override {
        Q_UNUSED(paramList);
        if (key.compare(QLatin1String("helm"), Qt::CaseInsensitive) == 0)
            return new HelmDecoration();
        return nullptr;
    }
};

#include "helmdecorationplugin.moc"
