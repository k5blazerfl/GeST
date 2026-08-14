#include "toplevelmodel.h"

namespace helm {

int indexOfKey(const QVector<Toplevel> &list, const QString &key) {
    for (int i = 0; i < list.size(); ++i)
        if (list[i].key == key)
            return i;
    return -1;
}

void upsert(QVector<Toplevel> &list, const Toplevel &t) {
    const int i = indexOfKey(list, t.key);
    if (i < 0)
        list.append(t);
    else
        list[i] = t;
}

void removeKey(QVector<Toplevel> &list, const QString &key) {
    const int i = indexOfKey(list, key);
    if (i >= 0)
        list.remove(i);
}

QString displayLabel(const Toplevel &t, int maxChars) {
    QString s = !t.title.isEmpty() ? t.title : t.appId;
    if (s.isEmpty())
        s = QStringLiteral("(untitled)");
    if (maxChars > 1 && s.size() > maxChars)
        s = s.left(maxChars - 1).trimmed() + QStringLiteral("…");
    return s;
}

} // namespace helm
