#pragma once

#include <QMainWindow>
#include <QStringList>

#include <functional>

class QAbstractItemView;
class QAction;
class QFileSystemModel;
class QListView;
class QListWidget;
class QModelIndex;
class QPoint;
class QStackedWidget;
class QTemporaryDir;
class QTreeView;

namespace helm::sefe {

class AddressBar;
class ArchiveModel;
class HelmThrobber;
class ThumbnailIconProvider;

// The SeFE main window. Slice 3 "Operations": read/write now — the full
// keyboard contract (F2 rename, Del → Trash, Ctrl+C/X/V, Ctrl+Shift+N new
// folder, F5 refresh, Alt+Enter properties) plus item/background context menus,
// on top of slice 2's Places pane + address bar + details/icons navigation.
// See docs/design/sefe.md.
class SefeWindow : public QMainWindow {
    Q_OBJECT
public:
    explicit SefeWindow(QWidget *parent = nullptr);
    ~SefeWindow() override;

protected:
    bool eventFilter(QObject *watched, QEvent *event) override;

private:
    // navigation (slice 2)
    void navigateTo(const QString &dir, bool record = true);
    void openIndex(const QModelIndex &index);
    void openArchiveEntry(const QString &inner); // extract-on-demand + open
    void goBack();
    void goForward();
    void goUp();
    void updateNavActions();
    void highlightPlace(const QString &dir);

    // operations (slice 3)
    void renameSelected();
    void deleteSelected();
    void copySelected(bool cut);
    void paste();
    void newFolder();
    void refresh();
    void showProperties();
    void openWith();
    void runInDrydock();  // .exe/.msi/.lnk → drydock open
    void shareFolder();   // a folder → gangway share (RDP drive)
    void copyPaths();     // selected paths → clipboard as text
    void extractHere();   // an archive → hold-core extract into the current dir
    void extractTo();     // an archive → hold-core extract into a chosen dir
    void compressSelection(); // selected paths → a new .zip via hold-core
    void showContextMenu(QAbstractItemView *view, const QPoint &pos);

    QAbstractItemView *activeView() const;
    QStringList selectedPaths() const;

    // Run `work` off the UI thread while the Helm throbber spins, then deliver
    // its result to `done` back on the UI thread. Keeps hold-core archive work
    // (extract/compress) from freezing the window — and makes the throbber spin
    // for real. Defined in window.cpp (only instantiated there).
    template <class Work, class Done>
    void runBusy(const QString &activity, Work work, Done done);

    QFileSystemModel *_model = nullptr;
    ThumbnailIconProvider *_iconProvider = nullptr; // owned; outlives the model
    ArchiveModel *_archiveModel = nullptr;          // owned; the archive being browsed
    bool _inArchive = false;                        // views are showing an archive
    QTemporaryDir *_extractTemp = nullptr;          // scratch for open-an-entry
    QTreeView *_details = nullptr;
    QListView *_icons = nullptr;
    QListWidget *_places = nullptr;
    QStackedWidget *_viewStack = nullptr;
    AddressBar *_address = nullptr;
    HelmThrobber *_throbber = nullptr; // Netscape-style busy light (top-right)

    QAction *_backAct = nullptr;
    QAction *_fwdAct = nullptr;
    QAction *_upAct = nullptr;
    QAction *_openAct = nullptr;
    QAction *_renameAct = nullptr;
    QAction *_deleteAct = nullptr;
    QAction *_copyAct = nullptr;
    QAction *_cutAct = nullptr;
    QAction *_pasteAct = nullptr;
    QAction *_newFolderAct = nullptr;
    QAction *_refreshAct = nullptr;
    QAction *_propsAct = nullptr;
    QAction *_openWithAct = nullptr;
    QAction *_drydockAct = nullptr;
    QAction *_shareAct = nullptr;
    QAction *_copyPathAct = nullptr;
    QAction *_extractHereAct = nullptr;
    QAction *_extractToAct = nullptr;
    QAction *_compressAct = nullptr;

    QString _current;
    QStringList _history;
    int _histIndex = -1;
    QStringList _clip; // cut/copied paths
    bool _clipCut = false;
};

} // namespace helm::sefe
