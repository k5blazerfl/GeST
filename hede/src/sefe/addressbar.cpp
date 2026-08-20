#include "addressbar.h"

#include "holdcore.h" // isArchive: mark the crumb where the filesystem enters an archive
#include "sefe.h"

#include <QEvent>
#include <QHBoxLayout>
#include <QKeyEvent>
#include <QLabel>
#include <QLineEdit>
#include <QStackedWidget>
#include <QToolButton>

namespace helm::sefe {

AddressBar::AddressBar(QWidget *parent) : QWidget(parent) {
    _stack = new QStackedWidget(this);

    _crumbs = new QWidget(_stack);
    _crumbLayout = new QHBoxLayout(_crumbs);
    _crumbLayout->setContentsMargins(4, 0, 4, 0);
    _crumbLayout->setSpacing(0);
    // A release on the empty part of the trail switches to the typeable field.
    _crumbs->installEventFilter(this);

    _edit = new QLineEdit(_stack);
    _edit->installEventFilter(this); // Esc cancels, focus-out cancels
    connect(_edit, &QLineEdit::returnPressed, this, &AddressBar::commitEdit);

    _stack->addWidget(_crumbs); // index 0 — breadcrumb mode
    _stack->addWidget(_edit);   // index 1 — edit mode

    auto *outer = new QHBoxLayout(this);
    outer->setContentsMargins(0, 0, 0, 0);
    outer->addWidget(_stack);
}

void AddressBar::setPath(const QString &dir) {
    _path = dir;
    rebuildCrumbs();
    _stack->setCurrentIndex(0);
}

void AddressBar::rebuildCrumbs() {
    // Clear the old buttons/separators.
    QLayoutItem *item = nullptr;
    while ((item = _crumbLayout->takeAt(0)) != nullptr) {
        if (auto *w = item->widget())
            w->deleteLater();
        delete item;
    }

    const QList<Crumb> crumbs = breadcrumbs(_path);
    for (int i = 0; i < crumbs.size(); ++i) {
        if (i > 0) {
            auto *sep = new QLabel(QStringLiteral("›"), _crumbs);
            sep->setEnabled(false);
            _crumbLayout->addWidget(sep);
        }
        auto *btn = new QToolButton(_crumbs);
        const QString target = crumbs[i].path;
        // The crumb that IS an archive gets an archive chip (🗜 + a pill style) —
        // it marks where the filesystem ends and browse-in-place begins.
        if (helm::hold::isArchive(target)) {
            btn->setObjectName(QStringLiteral("HelmCrumbArchive"));
            btn->setText(QStringLiteral("🗜 %1").arg(crumbs[i].label));
        } else {
            btn->setText(crumbs[i].label);
        }
        btn->setAutoRaise(true);
        connect(btn, &QToolButton::clicked, this,
                [this, target] { emit navigate(target); });
        _crumbLayout->addWidget(btn);
    }
    _crumbLayout->addStretch(1); // empty area → click to edit
}

void AddressBar::beginEdit() {
    _edit->setText(_path);
    _stack->setCurrentIndex(1);
    _edit->setFocus(Qt::ShortcutFocusReason);
    _edit->selectAll();
}

void AddressBar::commitEdit() {
    const QString target = normalizePath(_edit->text(), _path);
    endEdit();
    emit navigate(target);
}

void AddressBar::endEdit() {
    _stack->setCurrentIndex(0); // back to breadcrumbs; setPath refreshes them
}

bool AddressBar::eventFilter(QObject *watched, QEvent *event) {
    if (watched == _crumbs && event->type() == QEvent::MouseButtonRelease) {
        beginEdit();
        return true;
    }
    if (watched == _edit) {
        if (event->type() == QEvent::KeyPress
            && static_cast<QKeyEvent *>(event)->key() == Qt::Key_Escape) {
            endEdit();
            return true;
        }
        if (event->type() == QEvent::FocusOut && _stack->currentIndex() == 1) {
            endEdit(); // clicking away cancels the edit
        }
    }
    return QWidget::eventFilter(watched, event);
}

} // namespace helm::sefe
