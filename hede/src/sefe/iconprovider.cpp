#include "iconprovider.h"

#include <QFileInfo>
#include <QImage>
#include <QImageReader>
#include <QPixmap>
#include <QSet>

namespace helm::sefe {

namespace {
constexpr int kThumb = 128; // max thumbnail edge, px

bool isImage(const QString &suffix) {
    static const QSet<QString> imgs = {QStringLiteral("png"),  QStringLiteral("jpg"),
                                       QStringLiteral("jpeg"), QStringLiteral("gif"),
                                       QStringLiteral("bmp"),  QStringLiteral("webp")};
    return imgs.contains(suffix.toLower());
}
} // namespace

QIcon ThumbnailIconProvider::icon(const QFileInfo &info) const {
    if (!info.isFile() || !isImage(info.suffix()))
        return QFileIconProvider::icon(info);

    const QString key = info.absoluteFilePath();
    const auto it = _cache.constFind(key);
    if (it != _cache.constEnd() && it->mtime == info.lastModified())
        return it->icon;

    QImageReader reader(key);
    reader.setAutoTransform(true); // honour EXIF orientation
    QSize size = reader.size();
    if (size.isValid()) {
        size.scale(kThumb, kThumb, Qt::KeepAspectRatio); // scaled decode where supported
        reader.setScaledSize(size);
    }
    const QImage image = reader.read();
    if (image.isNull())
        return QFileIconProvider::icon(info); // unreadable → generic mimetype icon

    const QIcon thumb(QPixmap::fromImage(image));
    _cache.insert(key, {thumb, info.lastModified()});
    return thumb;
}

} // namespace helm::sefe
