#pragma once

#include <QString>
#include <QStringList>

namespace helm {

// The editable working state of a panel layout: the ordered applet ids the user
// is arranging, plus the mutation ops the editor drives. Pure (Core-only) so it
// unit-tests and can be reused by the Control Center "Panel Layout" module — the
// second door onto the same engine.
class PanelEditorModel {
  public:
    PanelEditorModel() = default;

    // Load the current layout from a hede.conf INI (via PanelLayout::read).
    void loadFrom(const QString &configPath);
    // Replace the working list wholesale — e.g. after a view's drag-reorder.
    void setApplets(const QStringList &applets);
    // Reset the working list to the built-in default lineup.
    void resetToDefault();

    // Mutations. Out-of-range indices are ignored; empty ids are not inserted.
    void moveItem(int from, int to); // reorder
    void removeAt(int index);        // drag-off / Delete
    void insert(int index, const QString &id);
    void append(const QString &id);

    // The current working order (what the bar would show).
    const QStringList &applets() const { return m_applets; }

    // Catalog ids the user can still add: every widget applet not already on the
    // bar, plus `spacer` (a gap, which may appear any number of times).
    QStringList available() const;

    // Persist the working list to a hede.conf INI (via PanelLayout::write); the
    // bar live-reloads. Returns false if the write failed.
    bool apply(const QString &configPath) const;

  private:
    QStringList m_applets;
};

} // namespace helm
