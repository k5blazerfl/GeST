#pragma once

#include <QString>
#include <QVector>

namespace helm {

// A window as seen through wlr-foreign-toplevel-management. `key` is an opaque,
// stable-per-lifetime identifier for the handle.
struct Toplevel {
    QString key;
    QString title;
    QString appId;
    bool activated = false;
    bool minimized = false;
};

// --- pure list operations (unit-tested; no Wayland involved) ---
int indexOfKey(const QVector<Toplevel> &list, const QString &key);
void upsert(QVector<Toplevel> &list, const Toplevel &t); // add, or replace by key
void removeKey(QVector<Toplevel> &list, const QString &key);

// Button text: title, else app-id, else a placeholder; elided to maxChars.
QString displayLabel(const Toplevel &t, int maxChars = 24);

} // namespace helm
