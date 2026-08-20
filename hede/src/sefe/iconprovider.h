#pragma once

#include <QDateTime>
#include <QFileIconProvider>
#include <QHash>
#include <QIcon>

namespace helm::sefe {

// A file icon provider that renders a scaled thumbnail for image files and
// defers to the default provider for everything else. Results are cached by
// path + mtime so scrolling a folder doesn't re-decode. Not a QObject — the
// window owns it and keeps it alive for the model's lifetime.
class ThumbnailIconProvider : public QFileIconProvider {
public:
    QIcon icon(const QFileInfo &info) const override;

private:
    struct Cached {
        QIcon icon;
        QDateTime mtime;
    };
    mutable QHash<QString, Cached> _cache;
};

} // namespace helm::sefe
