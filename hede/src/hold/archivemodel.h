#pragma once

#include <QAbstractItemModel>
#include <QDateTime>
#include <QList>
#include <QString>

// A tree model over an archive's entries (hold::list), so Seahorse can browse
// *into* an archive with the same views it uses for the filesystem — the
// browse-in-place experience (docs/design/hold.md, Hold H3). Core-only (no
// QIcon), so it lives in sefe-lib and is unit-tested headlessly.
namespace helm::hold {

class ArchiveModel : public QAbstractItemModel {
    Q_OBJECT
public:
    // Columns mirror QFileSystemModel's so the same views read naturally.
    enum Column { Name = 0, Size, Type, Modified, ColumnCount };

    explicit ArchiveModel(const QString &archivePath, QObject *parent = nullptr);
    ~ArchiveModel() override;

    QString archivePath() const { return _archivePath; }
    bool ok() const { return _ok; }

    // The entry's path inside the archive ("sub/a.txt") for an index, or "".
    QString innerPath(const QModelIndex &index) const;
    bool isDir(const QModelIndex &index) const;
    // The index (column 0) for an inner path — used to root a view at a subdir.
    // An empty inner returns an invalid index (the archive root).
    QModelIndex indexForInner(const QString &inner) const;

    // QAbstractItemModel
    QModelIndex index(int row, int column, const QModelIndex &parent) const override;
    QModelIndex parent(const QModelIndex &index) const override;
    int rowCount(const QModelIndex &parent) const override;
    int columnCount(const QModelIndex &parent) const override;
    QVariant data(const QModelIndex &index, int role) const override;
    QVariant headerData(int section, Qt::Orientation orientation, int role) const override;

private:
    struct Node {
        QString name;
        QString inner;
        qint64 size = 0;
        bool isDir = false;
        QDateTime mtime;
        Node *parent = nullptr;
        QList<Node *> children;
    };
    Node *nodeFor(const QModelIndex &index) const; // index → Node* (root if invalid)

    QString _archivePath;
    bool _ok = false;
    Node *_root = nullptr;
};

} // namespace helm::hold
