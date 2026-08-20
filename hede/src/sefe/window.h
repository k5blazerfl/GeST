#pragma once

#include "holdcore.h" // helm::hold::Result / Progress for runJob

#include <QColor>
#include <QMainWindow>
#include <QPixmap>
#include <QPoint>
#include <QStringList>

#include <functional>
#include <memory>
#include <optional>

class QAbstractItemModel;
class QAbstractItemView;
class QAction;
class QFileSystemModel;
class QLabel;
class QListView;
class QListWidget;
class QMenuBar;
class QModelIndex;
class QMouseEvent;
class QPaintEvent;
class QPoint;
class QStackedWidget;
class QTemporaryDir;
class QTreeView;

namespace helm::hold {
class ArchiveModel; // the archive tree model lives in the shared hold-core lib
}

namespace helm::sefe {

class AddressBar;
class HelmThrobber;
class HelmTitleBar;
class ThumbnailIconProvider;

// The SeFE main window. Slice 3 "Operations": read/write now — the full
// keyboard contract (F2 rename, Del → Trash, Ctrl+C/X/V, Ctrl+Shift+N new
// folder, F5 refresh, Alt+Enter properties) plus item/background context menus,
// on top of slice 2's Places pane + address bar + details/icons navigation.
// See docs/design/sefe.md.
class SefeWindow : public QMainWindow {
    Q_OBJECT
public:
    // `startPath` is an initial folder or archive to open (from the command line
    // / a file association); empty opens Home. Archives open browsed-in-place.
    explicit SefeWindow(const QString &startPath = QString(), QWidget *parent = nullptr);
    ~SefeWindow() override;

protected:
    bool eventFilter(QObject *watched, QEvent *event) override;
    // Frameless scene chrome (Phase D): paint the world scene + legibility scrims
    // behind the transparent chrome, and drive interactive move/resize since a
    // frameless toplevel has no server-side titlebar or resize border.
    void paintEvent(QPaintEvent *event) override;
    void mousePressEvent(QMouseEvent *event) override;
    void mouseMoveEvent(QMouseEvent *event) override;

private:
    // --- scene chrome (Phase D) ---
    void buildSceneChrome();          // frameless flags, titlebar, scene, insets
    void loadScene();                 // (re)load the active world's wallpaper
    Qt::Edges resizeEdgeAt(const QPoint &pos) const; // which border the cursor is on
    int headerHeight() const;         // top scrim band (titlebar+menu+toolbar)
    int footerHeight() const;         // bottom scrim band (status bar)

    // navigation (slice 2)
    void navigateTo(const QString &dir, bool record = true, bool forceReload = false);
    void setViewModel(QAbstractItemModel *m, const QModelIndex &root); // swap+root both views
    void finishNavigate(const QString &path, bool record); // address/title/history/pill
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
    // Rich archive ops, folded in from the former standalone Hold app: while
    // browsing inside an archive, extract the selected entries — or the whole
    // archive — to a chosen folder via hold-core. See docs/design/hold.md (H4).
    void extractSelectedEntries(); // selected inner entries → a chosen folder
    void extractWholeArchive();    // the whole current archive → a chosen folder
    // A2: mutate the browsed archive in place via hold::rewrite (off-thread) then
    // reload it. The in-archive delete / rename / new folder / paste route here.
    // `keepalive` (e.g. new-folder's temp dir) is held until the rewrite finishes.
    void mutateArchive(const helm::hold::Edits &edits, const QString &activity,
                       std::shared_ptr<QTemporaryDir> keepalive = {});
    void showContextMenu(QAbstractItemView *view, const QPoint &pos);

    // Menu bar (on by default; the whole File/Edit/View/Go/Tools/Help surface is
    // wired to the same QActions the toolbar and context menu use). View → Menu
    // Bar (Ctrl+M) hides it. See docs/design/seahorse-appearance.md.
    void buildMenuBar();
    void showAbout();

    QAbstractItemView *activeView() const;
    QStringList selectedPaths() const;
    QStringList selectedInnerEntries() const; // selected entries when browsing an archive
    // A2 drag-and-drop for archives: drag entries OUT (extract to the drop target via
    // a temp dir + file-URL QDrag) and drop files IN (add to the archive). Handled in
    // eventFilter on the view viewports.
    void startArchiveDrag();

    // Run `work` off the UI thread while the Helm throbber spins, then deliver
    // its result to `done` back on the UI thread. Keeps hold-core archive work
    // (extract/compress) from freezing the window — and makes the throbber spin
    // for real. Defined in window.cpp (only instantiated there).
    template <class Work, class Done>
    void runBusy(const QString &activity, Work work, Done done);

    // Run a hold-core op as a hold::Job: an in-window progress dialog (appears only
    // if the op runs past a short delay) with a Cancel button, the throbber, and a
    // status summary. The bar is determinate when the op reports a total, else
    // indeterminate. See docs/design/archive-support.md (A0).
    void runJob(const QString &title,
                std::function<helm::hold::Result(const helm::hold::Progress &)> work,
                std::function<QString(const helm::hold::Result &)> summary);

    // Pre-scan the extract destination for entries that already exist and, if any
    // do, prompt once for the overwrite policy (Replace / Keep Both / Skip). Returns
    // the chosen policy, or nullopt if the user cancels. No collision → Replace (a
    // no-op — nothing to overwrite), no prompt. See docs/design/archive-support.md
    // (A1, decision D). `relPaths` are archive-relative entry paths.
    std::optional<helm::hold::Overwrite> resolveOverwrite(const QString &dest,
                                                          const QStringList &relPaths);

    QFileSystemModel *_model = nullptr;
    ThumbnailIconProvider *_iconProvider = nullptr; // owned; outlives the model
    helm::hold::ArchiveModel *_archiveModel = nullptr; // owned; the archive being browsed
    bool _inArchive = false;                        // views are showing an archive
    QTemporaryDir *_extractTemp = nullptr;          // scratch for open-an-entry
    QTreeView *_details = nullptr;
    QListView *_icons = nullptr;
    QListWidget *_places = nullptr;
    QStackedWidget *_viewStack = nullptr;
    AddressBar *_address = nullptr;
    HelmThrobber *_throbber = nullptr; // Netscape-style busy light (top-right)
    HelmTitleBar *_titlebar = nullptr; // client-side titlebar (frameless chrome)
    QMenuBar *_menuBar = nullptr;      // our menu bar (lives in the header widget)
    QLabel *_readOnlyPill = nullptr;   // status-bar "🗜 Read-only" pill, shown in an archive
    QPixmap _scene;                    // the active world's wallpaper, painted as chrome
    QColor _accent;                    // effective accent (scene-less fallback fill)
    static constexpr int kResizeMargin = 7; // edge band that starts a system resize

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
    QAction *_arcExtractSelAct = nullptr; // in-archive: Extract Selected…
    QAction *_arcExtractAllAct = nullptr; // in-archive: Extract All…
    QAction *_viewToggleAct = nullptr; // Details ⇄ Icons (also the toolbar button)
    QAction *_selectAllAct = nullptr;
    QAction *_menuBarAct = nullptr;     // View → Menu Bar (checkable, Ctrl+M)

    QString _current;
    QPoint _dragStartPos; // press point, to detect a drag-out gesture in an archive
    quint64 _navGen = 0; // bumped per navigateTo; async archive loads drop if superseded
    QStringList _history;
    int _histIndex = -1;
    QStringList _clip; // cut/copied paths
    bool _clipCut = false;
};

} // namespace helm::sefe
