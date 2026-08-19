#pragma once

#include <QMainWindow>

namespace helm::sefe {

// The SeFE main window. Slice 1 "Hull": a read-only tree view of the home
// directory, themed by the shell palette. Navigation (Places pane, address bar),
// operations, and interop land in later slices — see docs/design/sefe.md.
class SefeWindow : public QMainWindow {
    Q_OBJECT
public:
    explicit SefeWindow(QWidget *parent = nullptr);
};

} // namespace helm::sefe
