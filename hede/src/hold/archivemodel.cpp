#include "archivemodel.h"

#include "holdcore.h"

#include <QLocale>

#include <algorithm>
#include <functional>

namespace helm::hold {

namespace {
// A child of `parent` named `name`, or nullptr.
template <typename Node> Node *childNamed(Node *parent, const QString &name) {
    for (Node *c : parent->children) {
        if (c->name == name)
            return c;
    }
    return nullptr;
}
} // namespace

ArchiveModel::ArchiveModel(const QString &archivePath, QObject *parent)
    : ArchiveModel(archivePath, helm::hold::list(archivePath), parent) {}

ArchiveModel::ArchiveModel(const QString &archivePath, const helm::hold::Listing &listing,
                           QObject *parent)
    : QAbstractItemModel(parent), _archivePath(archivePath) {
    _root = new Node; // the invisible root; its children are the top-level entries
    buildTree(listing);
}

void ArchiveModel::buildTree(const helm::hold::Listing &listing) {
    _ok = listing.ok;
    for (const helm::hold::Entry &e : listing.entries) {
        const QStringList parts = e.path.split(QLatin1Char('/'), Qt::SkipEmptyParts);
        Node *cur = _root;
        QString acc;
        for (int j = 0; j < parts.size(); ++j) {
            acc = acc.isEmpty() ? parts[j] : acc + QLatin1Char('/') + parts[j];
            const bool last = (j == parts.size() - 1);
            Node *child = childNamed(cur, parts[j]);
            if (!child) {
                child = new Node;
                child->name = parts[j];
                child->inner = acc;
                child->parent = cur;
                child->isDir = last ? e.isDir : true; // intermediates are dirs
                cur->children.append(child);
            }
            if (last) { // the entry's own row: record its real metadata
                child->size = e.size;
                child->mtime = e.mtime;
                if (e.isDir)
                    child->isDir = true;
            }
            cur = child;
        }
    }

    // Sort every level: directories first, then case-insensitive by name.
    std::function<void(Node *)> sortRec = [&](Node *n) {
        std::sort(n->children.begin(), n->children.end(), [](Node *a, Node *b) {
            if (a->isDir != b->isDir)
                return a->isDir; // dirs before files
            return a->name.compare(b->name, Qt::CaseInsensitive) < 0;
        });
        for (Node *c : n->children)
            sortRec(c);
    };
    sortRec(_root);
}

ArchiveModel::~ArchiveModel() {
    std::function<void(Node *)> del = [&](Node *n) {
        for (Node *c : n->children)
            del(c);
        delete n;
    };
    del(_root);
}

ArchiveModel::Node *ArchiveModel::nodeFor(const QModelIndex &index) const {
    return index.isValid() ? static_cast<Node *>(index.internalPointer()) : _root;
}

QString ArchiveModel::innerPath(const QModelIndex &index) const {
    const Node *n = index.isValid() ? static_cast<const Node *>(index.internalPointer()) : nullptr;
    return n ? n->inner : QString();
}

bool ArchiveModel::isDir(const QModelIndex &index) const {
    const Node *n = index.isValid() ? static_cast<const Node *>(index.internalPointer()) : nullptr;
    return n && n->isDir;
}

QModelIndex ArchiveModel::indexForInner(const QString &inner) const {
    if (inner.isEmpty())
        return {};
    Node *cur = _root;
    for (const QString &part : inner.split(QLatin1Char('/'), Qt::SkipEmptyParts)) {
        Node *next = childNamed(cur, part);
        if (!next)
            return {};
        cur = next;
    }
    if (cur == _root || !cur->parent)
        return {};
    const int row = cur->parent->children.indexOf(cur);
    return createIndex(row, 0, cur);
}

QModelIndex ArchiveModel::index(int row, int column, const QModelIndex &parent) const {
    if (!hasIndex(row, column, parent))
        return {};
    Node *p = nodeFor(parent);
    return createIndex(row, column, p->children.at(row));
}

QModelIndex ArchiveModel::parent(const QModelIndex &index) const {
    if (!index.isValid())
        return {};
    Node *n = static_cast<Node *>(index.internalPointer());
    Node *p = n->parent;
    if (!p || p == _root)
        return {};
    const int row = p->parent->children.indexOf(p);
    return createIndex(row, 0, p);
}

int ArchiveModel::rowCount(const QModelIndex &parent) const {
    if (parent.column() > 0)
        return 0;
    return nodeFor(parent)->children.size();
}

int ArchiveModel::columnCount(const QModelIndex &) const { return ColumnCount; }

QVariant ArchiveModel::data(const QModelIndex &index, int role) const {
    if (!index.isValid())
        return {};
    const Node *n = static_cast<const Node *>(index.internalPointer());
    if (role == Qt::DisplayRole) {
        switch (index.column()) {
        case Name:
            return n->name;
        case Size:
            return n->isDir ? QString() : QLocale().formattedDataSize(n->size);
        case Type:
            return n->isDir ? QStringLiteral("Folder") : QStringLiteral("File");
        case Modified:
            return n->mtime.isValid() ? n->mtime.toString(Qt::TextDate) : QString();
        }
    }
    return {};
}

QVariant ArchiveModel::headerData(int section, Qt::Orientation orientation, int role) const {
    if (orientation != Qt::Horizontal || role != Qt::DisplayRole)
        return {};
    switch (section) {
    case Name:
        return QStringLiteral("Name");
    case Size:
        return QStringLiteral("Size");
    case Type:
        return QStringLiteral("Type");
    case Modified:
        return QStringLiteral("Modified");
    }
    return {};
}

} // namespace helm::hold
