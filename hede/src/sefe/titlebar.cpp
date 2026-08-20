#include "titlebar.h"

#include <QHBoxLayout>
#include <QLabel>
#include <QMouseEvent>
#include <QToolButton>
#include <QWindow>

namespace helm::sefe {

HelmTitleBar::HelmTitleBar(QWidget *parent) : QWidget(parent) {
    setObjectName(QStringLiteral("HelmTitleBar"));
    setFixedHeight(34);

    auto *lay = new QHBoxLayout(this);
    lay->setContentsMargins(12, 0, 6, 0);
    lay->setSpacing(2);

    _title = new QLabel(this);
    _title->setObjectName(QStringLiteral("HelmTitleText"));

    // Window controls on the right, Windows-familiar order: minimize, maximize,
    // close. Glyphs are drawn as text so they inherit the light chrome colour and
    // need no icon theme; close gets a hover-red tint via QSS (#HelmWinClose).
    const auto control = [this](const QString &objectName, const QString &glyph) {
        auto *b = new QToolButton(this);
        b->setObjectName(objectName);
        b->setText(glyph);
        b->setFocusPolicy(Qt::NoFocus);
        b->setFixedSize(30, 24);
        return b;
    };
    auto *minBtn = control(QStringLiteral("HelmWinButton"), QStringLiteral("–"));   // –
    auto *maxBtn = control(QStringLiteral("HelmWinButton"), QStringLiteral("□"));    // □
    auto *closeBtn = control(QStringLiteral("HelmWinClose"), QStringLiteral("✕"));   // ✕

    lay->addWidget(_title);
    lay->addStretch(1);
    lay->addWidget(minBtn);
    lay->addWidget(maxBtn);
    lay->addWidget(closeBtn);

    connect(minBtn, &QToolButton::clicked, this, [this] { window()->showMinimized(); });
    connect(maxBtn, &QToolButton::clicked, this, &HelmTitleBar::toggleMaximize);
    connect(closeBtn, &QToolButton::clicked, this, [this] { window()->close(); });
}

void HelmTitleBar::setTitle(const QString &title) { _title->setText(title); }

void HelmTitleBar::toggleMaximize() {
    QWidget *w = window();
    if (w->isMaximized())
        w->showNormal();
    else
        w->showMaximized();
}

void HelmTitleBar::mousePressEvent(QMouseEvent *event) {
    // Drag the titlebar → ask the compositor to move the toplevel (Wayland has no
    // absolute window positioning; this is xdg_toplevel.move under the hood).
    if (event->button() == Qt::LeftButton) {
        if (QWindow *handle = window()->windowHandle())
            handle->startSystemMove();
    }
    QWidget::mousePressEvent(event);
}

void HelmTitleBar::mouseDoubleClickEvent(QMouseEvent *event) {
    if (event->button() == Qt::LeftButton)
        toggleMaximize();
    QWidget::mouseDoubleClickEvent(event);
}

} // namespace helm::sefe
