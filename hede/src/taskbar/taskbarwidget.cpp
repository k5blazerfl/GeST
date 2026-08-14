#include "taskbarwidget.h"

#include "foreigntoplevel.h"

#include <QHBoxLayout>
#include <QMouseEvent>
#include <QToolButton>

#include <functional>
#include <utility>

namespace helm {

// A task button that also reports middle-clicks (used to close the window).
// No Q_OBJECT needed: it reuses QToolButton::clicked and adds a plain callback.
class TaskButton : public QToolButton {
  public:
    explicit TaskButton(QWidget *parent) : QToolButton(parent) {}
    std::function<void()> onMiddleClick;

  protected:
    void mouseReleaseEvent(QMouseEvent *e) override {
        if (e->button() == Qt::MiddleButton && onMiddleClick) {
            onMiddleClick();
            return;
        }
        QToolButton::mouseReleaseEvent(e);
    }
};

TaskbarWidget::TaskbarWidget(QWidget *parent)
    : QWidget(parent), m_manager(new ForeignToplevelManager) {
    m_manager->setParent(this);
    m_layout = new QHBoxLayout(this);
    m_layout->setContentsMargins(0, 0, 0, 0);
    m_layout->setSpacing(4);
    m_layout->addStretch(1);

    connect(m_manager, &ForeignToplevelManager::toplevelChanged, this, &TaskbarWidget::onChanged);
    connect(m_manager, &ForeignToplevelManager::toplevelClosed, this, &TaskbarWidget::onClosed);
}

void TaskbarWidget::onChanged(const Toplevel &t) {
    upsert(m_items, t);
    rebuild();
}

void TaskbarWidget::onClosed(const QString &key) {
    removeKey(m_items, key);
    rebuild();
}

void TaskbarWidget::rebuild() {
    // Clear existing children (buttons + the trailing stretch), then re-add.
    QLayoutItem *item;
    while ((item = m_layout->takeAt(0)) != nullptr) {
        if (item->widget())
            item->widget()->deleteLater();
        delete item;
    }

    for (const Toplevel &t : std::as_const(m_items)) {
        auto *btn = new TaskButton(this);
        btn->setText(displayLabel(t));
        btn->setCheckable(true);
        btn->setChecked(t.activated && !t.minimized);
        btn->setToolButtonStyle(Qt::ToolButtonTextOnly);
        if (!t.title.isEmpty())
            btn->setToolTip(t.title);

        const QString key = t.key;
        connect(btn, &QToolButton::clicked, this, [this, key] {
            const int i = indexOfKey(m_items, key);
            if (i < 0)
                return;
            if (m_items[i].activated && !m_items[i].minimized)
                m_manager->toggleMinimize(key);
            else
                m_manager->activate(key);
        });
        btn->onMiddleClick = [this, key] { m_manager->close(key); };

        m_layout->addWidget(btn);
    }
    m_layout->addStretch(1);
}

} // namespace helm
