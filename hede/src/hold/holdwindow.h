#pragma once

#include <QMainWindow>
#include <QStringList>

class QModelIndex;
class QTemporaryDir;
class QTreeView;

namespace helm::hold {

class ArchiveModel;

// Hold — the standalone archive manager (docs/design/hold.md, H4). Opens one
// archive, browses it with the shared ArchiveModel, and extracts (all or the
// selection). The rich path (passwords, formats, a create wizard, batch
// progress) builds out from here; Seahorse handles the inline everyday path.
class HoldWindow : public QMainWindow {
    Q_OBJECT
public:
    explicit HoldWindow(const QString &archivePath, QWidget *parent = nullptr);
    ~HoldWindow() override;

private:
    void extractAll();
    void extractSelected();
    void openEntry(const QModelIndex &index); // extract-on-demand + open a file
    QStringList selectedInner() const;        // inner paths of the selection

    QString _archive;
    ArchiveModel *_model = nullptr;
    QTreeView *_view = nullptr;
    QTemporaryDir *_temp = nullptr; // scratch for opened entries
};

} // namespace helm::hold
