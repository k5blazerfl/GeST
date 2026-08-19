#pragma once

#include <QMainWindow>
#include <QStringList>

class QAction;
class QFileSystemModel;
class QListView;
class QListWidget;
class QModelIndex;
class QStackedWidget;
class QTreeView;

namespace helm::sefe {

class AddressBar;

// The SeFE main window. Slice 2 "Navigation": a Places pane, a breadcrumb /
// typeable address bar, details + icons views over a shared QFileSystemModel,
// and Back/Forward/Up history — double-click opens (folder → navigate, file →
// default handler), single-click selects. Read-only still; file operations land
// in slice 3 (see docs/design/sefe.md).
class SefeWindow : public QMainWindow {
    Q_OBJECT
public:
    explicit SefeWindow(QWidget *parent = nullptr);

private:
    void navigateTo(const QString &dir, bool record = true);
    void openIndex(const QModelIndex &index);
    void goBack();
    void goForward();
    void goUp();
    void updateNavActions();
    void highlightPlace(const QString &dir);

    QFileSystemModel *_model = nullptr;
    QTreeView *_details = nullptr;
    QListView *_icons = nullptr;
    QListWidget *_places = nullptr;
    QStackedWidget *_viewStack = nullptr;
    AddressBar *_address = nullptr;
    QAction *_backAct = nullptr;
    QAction *_fwdAct = nullptr;
    QAction *_upAct = nullptr;

    QString _current;
    QStringList _history; // visited dirs; _histIndex is the current position
    int _histIndex = -1;
};

} // namespace helm::sefe
