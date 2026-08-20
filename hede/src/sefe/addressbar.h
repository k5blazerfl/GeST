#pragma once

#include <QWidget>

class QHBoxLayout;
class QLineEdit;
class QStackedWidget;

namespace helm::sefe {

// The SeFE address bar: a breadcrumb trail by default (Windows-familiar), that
// clicks into a typeable path field — click the empty part of the bar or press
// Ctrl+L to edit, Enter to go, Esc to cancel. Emits navigate() with an absolute
// path for both a crumb click and a committed edit.
class AddressBar : public QWidget {
    Q_OBJECT
public:
    explicit AddressBar(QWidget *parent = nullptr);

    QString path() const { return _path; }

public slots:
    void setPath(const QString &dir); // show `dir` as breadcrumbs
    void beginEdit();                 // switch to the typeable field

signals:
    void navigate(const QString &path);

protected:
    bool eventFilter(QObject *watched, QEvent *event) override;

private:
    void rebuildCrumbs();
    void commitEdit();
    void endEdit();

    QString _path;
    QStackedWidget *_stack = nullptr;
    QWidget *_crumbs = nullptr;
    QHBoxLayout *_crumbLayout = nullptr;
    QLineEdit *_edit = nullptr;
};

} // namespace helm::sefe
