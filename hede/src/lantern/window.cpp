#include "window.h"

#include "client.h"
#include "format.h"
#include "notification.h"

#include <QCheckBox>
#include <QDateTime>
#include <QEvent>
#include <QFont>
#include <QFrame>
#include <QHBoxLayout>
#include <QKeyEvent>
#include <QLabel>
#include <QLayoutItem>
#include <QPushButton>
#include <QScrollArea>
#include <QSignalBlocker>
#include <QVBoxLayout>

namespace helm {

static QWidget *makeEntry(const Notification &n, const QDateTime &now) {
    auto *frame = new QFrame;
    frame->setObjectName(QStringLiteral("LanternEntry"));
    frame->setFrameShape(QFrame::StyledPanel);
    auto *v = new QVBoxLayout(frame);
    v->setContentsMargins(10, 8, 10, 8);
    v->setSpacing(2);

    auto *title = new QLabel(entryTitle(n), frame);
    title->setObjectName(QStringLiteral("LanternEntryTitle"));
    QFont tf = title->font();
    tf.setBold(true);
    title->setFont(tf);
    title->setWordWrap(true);
    v->addWidget(title);

    const QString body = n.body.trimmed();
    if (!body.isEmpty()) {
        auto *b = new QLabel(body, frame);
        b->setObjectName(QStringLiteral("LanternEntryBody"));
        b->setWordWrap(true);
        b->setTextFormat(Qt::PlainText); // app-supplied text, not rich markup
        v->addWidget(b);
    }
    const QString when = relativeTime(n.received, now);
    if (!when.isEmpty()) {
        auto *t = new QLabel(when, frame);
        t->setObjectName(QStringLiteral("LanternEntryTime"));
        t->setEnabled(false); // muted
        v->addWidget(t);
    }
    return frame;
}

LanternWindow::LanternWindow(QWidget *parent) : QWidget(parent) {
    setObjectName(QStringLiteral("LanternPanel"));
    setWindowTitle(tr("Notifications"));
    setFixedWidth(380);

    m_client = new LanternClient(this);

    // Header: title, Do-Not-Disturb toggle, Clear all.
    auto *heading = new QLabel(tr("Notifications"), this);
    heading->setObjectName(QStringLiteral("LanternHeading"));
    m_dnd = new QCheckBox(tr("Do Not Disturb"), this);
    m_dnd->setChecked(m_client->doNotDisturb()); // set before wiring → no spurious call
    auto *clear = new QPushButton(tr("Clear all"), this);

    auto *header = new QHBoxLayout;
    header->addWidget(heading);
    header->addStretch();
    header->addWidget(m_dnd);
    header->addWidget(clear);

    // Scrollable entries column, top-aligned by a trailing stretch.
    auto *scroll = new QScrollArea(this);
    scroll->setWidgetResizable(true);
    scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    auto *listHost = new QWidget;
    m_list = new QVBoxLayout(listHost);
    m_list->setContentsMargins(8, 8, 8, 8);
    m_list->setSpacing(6);
    m_list->addStretch();
    scroll->setWidget(listHost);

    auto *root = new QVBoxLayout(this);
    root->addLayout(header);
    root->addWidget(scroll, 1);

    connect(clear, &QPushButton::clicked, this, [this] { m_client->clearHistory(); });
    connect(m_dnd, &QCheckBox::toggled, this, [this](bool on) { m_client->setDoNotDisturb(on); });
    connect(m_client, &LanternClient::historyChanged, this, &LanternWindow::rebuild);
    connect(m_client, &LanternClient::dndChanged, this, [this](bool on) {
        const QSignalBlocker block(m_dnd); // reflect the daemon without re-calling it
        m_dnd->setChecked(on);
    });

    rebuild();
}

void LanternWindow::rebuild() {
    // Drop the current entries (everything before the trailing stretch).
    while (m_list->count() > 1) {
        QLayoutItem *item = m_list->takeAt(0);
        if (QWidget *w = item->widget())
            w->deleteLater();
        delete item;
    }

    const QVector<Notification> hist = m_client->history();
    if (hist.isEmpty()) {
        auto *empty = new QLabel(tr("No notifications"), this);
        empty->setObjectName(QStringLiteral("LanternEmpty"));
        empty->setAlignment(Qt::AlignCenter);
        empty->setEnabled(false);
        m_list->insertWidget(0, empty);
        return;
    }
    const QDateTime now = QDateTime::currentDateTime();
    for (int i = 0; i < hist.size(); ++i) // GetHistory is already newest-first
        m_list->insertWidget(i, makeEntry(hist[i], now));
}

void LanternWindow::keyPressEvent(QKeyEvent *e) {
    if (e->key() == Qt::Key_Escape) {
        close();
        return;
    }
    QWidget::keyPressEvent(e);
}

bool LanternWindow::event(QEvent *e) {
    if (e->type() == QEvent::WindowActivate)
        m_activated = true;
    else if (e->type() == QEvent::WindowDeactivate && m_activated)
        close(); // click-away — but not the deactivate that can precede first show
    return QWidget::event(e);
}

} // namespace helm
