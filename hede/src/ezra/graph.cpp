#include "graph.h"

#include <QPainter>
#include <QPainterPath>

namespace ezra {

namespace {
constexpr int kSamples = 60; // one minute of history at the 1 s tick
}

HistoryGraph::HistoryGraph(const QString &title, Scale scale, QWidget *parent,
                           const QSize &minSize)
    : QWidget(parent), title_(title), scale_(scale), minSize_(minSize) {
    setMinimumSize(minimumSizeHint());
}

void HistoryGraph::push(double value, const QString &caption) {
    history_.append(qMax(0.0, value));
    if (history_.size() > kSamples)
        history_.removeFirst();
    caption_ = caption;
    update();
}

void HistoryGraph::paintEvent(QPaintEvent *) {
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);

    const QPalette pal = palette();
    const QColor accent = pal.color(QPalette::Highlight);
    QColor frame = pal.color(QPalette::Mid);

    const QFontMetrics fm(font());
    const int headerH = fm.height() + 4;
    const QRectF plot = QRectF(rect()).adjusted(0.5, headerH + 0.5, -0.5, -0.5);

    // Header: the caption (current value) keeps the right side; the title is
    // elided into whatever is left so the two never collide on narrow tiles.
    painter.setPen(pal.color(QPalette::WindowText));
    const int captionW = fm.horizontalAdvance(caption_);
    painter.drawText(QRectF(0, 0, width(), headerH), Qt::AlignRight | Qt::AlignVCenter, caption_);
    const QString title =
        fm.elidedText(title_, Qt::ElideRight, qMax(0, width() - captionW - 8));
    painter.drawText(QRectF(0, 0, width(), headerH), Qt::AlignLeft | Qt::AlignVCenter, title);

    // Plot frame + midline.
    painter.setPen(frame);
    painter.setBrush(pal.color(QPalette::Base));
    painter.drawRect(plot);
    frame.setAlphaF(0.4f);
    painter.setPen(frame);
    painter.drawLine(QPointF(plot.left(), plot.center().y()),
                     QPointF(plot.right(), plot.center().y()));

    if (history_.isEmpty())
        return;

    double top = 100.0;
    if (scale_ == AutoScale) {
        top = 1.0; // avoid a flat line dividing by zero
        for (double v : history_)
            top = qMax(top, v);
        top *= 1.1; // headroom so the peak isn't glued to the frame
    }

    // Newest sample pinned to the right edge, one slot per sample.
    const double dx = plot.width() / double(kSamples - 1);
    QPainterPath line;
    for (int i = 0; i < history_.size(); ++i) {
        const double x = plot.right() - dx * double(history_.size() - 1 - i);
        const double y =
            plot.bottom() - qMin(history_.at(i), top) / top * plot.height();
        if (i == 0)
            line.moveTo(x, y);
        else
            line.lineTo(x, y);
    }

    QPainterPath fill = line;
    fill.lineTo(plot.right(), plot.bottom());
    fill.lineTo(plot.right() - dx * double(history_.size() - 1), plot.bottom());
    fill.closeSubpath();
    QColor fillColor = accent;
    fillColor.setAlphaF(0.18f);
    painter.fillPath(fill, fillColor);

    painter.setPen(QPen(accent, 1.5));
    painter.setBrush(Qt::NoBrush);
    painter.setClipRect(plot);
    painter.drawPath(line);
}

} // namespace ezra
