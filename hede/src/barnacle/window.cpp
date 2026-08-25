#include "window.h"

#include "catalog.h"
#include "config.h"
#include "layout.h"

#include <QAbstractItemView>
#include <QComboBox>
#include <QHBoxLayout>
#include <QLabel>
#include <QListWidget>
#include <QPushButton>
#include <QSignalBlocker>
#include <QVBoxLayout>

namespace helm {

static QString labelFor(const QString &id) {
    if (const AppletInfo *a = findApplet(id))
        return a->label;
    return id; // an unknown id still shows, so a hand-edit isn't silently lost
}

static QListWidgetItem *makeItem(const QString &id) {
    auto *item = new QListWidgetItem(labelFor(id));
    item->setData(Qt::UserRole, id);
    return item;
}

BarnacleWindow::BarnacleWindow(QWidget *parent) : QWidget(parent) {
    setWindowTitle(tr("Barnacle — Panel Layout"));

    m_configPath = Config().path();
    m_model.loadFrom(m_configPath);

    // "On the bar": the live layout, reordered by dragging rows.
    m_barList = new QListWidget(this);
    m_barList->setSelectionMode(QAbstractItemView::SingleSelection);
    m_barList->setDragDropMode(QAbstractItemView::InternalMove);
    m_barList->setDefaultDropAction(Qt::MoveAction);

    // "Available": catalog applets not yet on the bar (plus the repeatable gap).
    m_availList = new QListWidget(this);
    m_availList->setSelectionMode(QAbstractItemView::SingleSelection);

    auto *addBtn = new QPushButton(tr("Add →"), this);
    auto *removeBtn = new QPushButton(tr("← Remove"), this);
    auto *resetBtn = new QPushButton(tr("Reset to default"), this);

    auto *left = new QVBoxLayout;
    left->addWidget(new QLabel(tr("On the bar"), this));
    left->addWidget(m_barList);

    auto *mid = new QVBoxLayout;
    mid->addStretch();
    mid->addWidget(addBtn);
    mid->addWidget(removeBtn);
    mid->addStretch();

    auto *right = new QVBoxLayout;
    right->addWidget(new QLabel(tr("Available"), this));
    right->addWidget(m_availList);

    auto *cols = new QHBoxLayout;
    cols->addLayout(left, 1);
    cols->addLayout(mid);
    cols->addLayout(right, 1);

    // Position: which screen edge the bar anchors to. Set the current value
    // before wiring the signal so building the row doesn't spuriously re-apply.
    m_edgeCombo = new QComboBox(this);
    for (const QString &e : PanelLayout::validEdges())
        m_edgeCombo->addItem(e == QLatin1String("top") ? tr("Top") : tr("Bottom"), e);
    const int edgeIdx = m_edgeCombo->findData(m_model.edge());
    if (edgeIdx >= 0)
        m_edgeCombo->setCurrentIndex(edgeIdx);

    auto *posRow = new QHBoxLayout;
    posRow->addWidget(new QLabel(tr("Position:"), this));
    posRow->addWidget(m_edgeCombo);
    posRow->addStretch();

    auto *bottom = new QHBoxLayout;
    bottom->addWidget(resetBtn);
    bottom->addStretch();
    bottom->addWidget(new QLabel(tr("Changes apply to the bar immediately."), this));

    auto *root = new QVBoxLayout(this);
    root->addLayout(posRow);
    root->addLayout(cols, 1);
    root->addLayout(bottom);

    connect(addBtn, &QPushButton::clicked, this, &BarnacleWindow::addSelected);
    connect(removeBtn, &QPushButton::clicked, this, &BarnacleWindow::removeSelected);
    connect(resetBtn, &QPushButton::clicked, this, [this] {
        m_model.resetToDefault();
        {
            const QSignalBlocker block(m_edgeCombo); // reflect edge without re-applying
            const int idx = m_edgeCombo->findData(m_model.edge());
            if (idx >= 0)
                m_edgeCombo->setCurrentIndex(idx);
        }
        rebuildLists();
        applyNow();
    });
    connect(m_edgeCombo, &QComboBox::currentIndexChanged, this, [this](int) {
        m_model.setEdge(m_edgeCombo->currentData().toString());
        applyNow(); // no list change; the bar re-anchors on reload
    });
    connect(m_availList, &QListWidget::itemDoubleClicked, this, &BarnacleWindow::addSelected);
    connect(m_barList, &QListWidget::itemDoubleClicked, this, &BarnacleWindow::removeSelected);
    // A drag-reorder rearranges the bar list's underlying rows; read the new
    // order back out and persist it. (clear()/addItem() in rebuildLists emit
    // rows-removed/-inserted, never rows-moved, so this can't recurse.)
    connect(m_barList->model(), &QAbstractItemModel::rowsMoved, this,
            &BarnacleWindow::syncFromBarList);

    rebuildLists();
    resize(560, 420);
}

void BarnacleWindow::rebuildLists() {
    const QSignalBlocker b1(m_barList);
    const QSignalBlocker b2(m_availList);
    m_barList->clear();
    for (const QString &id : m_model.applets())
        m_barList->addItem(makeItem(id));
    m_availList->clear();
    for (const QString &id : m_model.available())
        m_availList->addItem(makeItem(id));
}

void BarnacleWindow::syncFromBarList() {
    QStringList ids;
    ids.reserve(m_barList->count());
    for (int i = 0; i < m_barList->count(); ++i)
        ids.append(m_barList->item(i)->data(Qt::UserRole).toString());
    m_model.setApplets(ids);
    rebuildLists(); // Available may have changed; also refreshes labels
    applyNow();
}

void BarnacleWindow::addSelected() {
    QListWidgetItem *sel = m_availList->currentItem();
    if (!sel)
        return;
    m_model.append(sel->data(Qt::UserRole).toString());
    rebuildLists();
    applyNow();
}

void BarnacleWindow::removeSelected() {
    const int row = m_barList->currentRow();
    if (row < 0)
        return;
    m_model.removeAt(row);
    rebuildLists();
    applyNow();
}

void BarnacleWindow::applyNow() { m_model.apply(m_configPath); }

} // namespace helm
