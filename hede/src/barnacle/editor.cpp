#include "editor.h"

#include "catalog.h"
#include "layout.h"

namespace helm {

void PanelEditorModel::loadFrom(const QString &configPath) {
    m_applets = PanelLayout::read(configPath);
}

void PanelEditorModel::setApplets(const QStringList &applets) { m_applets = applets; }

void PanelEditorModel::resetToDefault() { m_applets = defaultApplets(); }

void PanelEditorModel::moveItem(int from, int to) {
    if (from < 0 || from >= m_applets.size())
        return;
    if (to < 0 || to >= m_applets.size())
        return;
    if (from == to)
        return;
    m_applets.move(from, to);
}

void PanelEditorModel::removeAt(int index) {
    if (index < 0 || index >= m_applets.size())
        return;
    m_applets.removeAt(index);
}

void PanelEditorModel::insert(int index, const QString &id) {
    if (id.isEmpty())
        return;
    const int at = qBound(0, index, m_applets.size());
    m_applets.insert(at, id);
}

void PanelEditorModel::append(const QString &id) { insert(m_applets.size(), id); }

QStringList PanelEditorModel::available() const {
    QStringList out;
    for (const AppletInfo &a : appletCatalog()) {
        // A gap can appear any number of times; a widget applet only once.
        if (a.kind == AppletKind::Stretch || !m_applets.contains(a.id))
            out.append(a.id);
    }
    return out;
}

bool PanelEditorModel::apply(const QString &configPath) const {
    return PanelLayout::write(configPath, m_applets);
}

} // namespace helm
