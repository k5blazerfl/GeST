#include "graph.h"

#include <QPainter>
#include <QPainterPath>

#include <cmath>

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

namespace {

// Shared header + frame: caption keeps the right side but never the whole
// width, title elides into what's left, then the framed plot area with a
// faint midline is returned.
QRectF paintHeaderAndFrame(QPainter &painter, const QWidget *w, const QString &titleText,
                           const QString &captionText) {
    const QPalette pal = w->palette();
    const QFontMetrics fm(w->font());
    const int headerH = fm.height() + 4;
    const QRectF plot = QRectF(w->rect()).adjusted(0.5, headerH + 0.5, -0.5, -0.5);

    painter.setPen(pal.color(QPalette::WindowText));
    const int titleMin = qMin(fm.horizontalAdvance(titleText), fm.horizontalAdvance(u'M') * 4);
    const QString caption =
        fm.elidedText(captionText, Qt::ElideRight, qMax(0, w->width() - titleMin - 8));
    painter.drawText(QRectF(0, 0, w->width(), headerH), Qt::AlignRight | Qt::AlignVCenter,
                     caption);
    const QString title = fm.elidedText(
        titleText, Qt::ElideRight, qMax(0, w->width() - fm.horizontalAdvance(caption) - 8));
    painter.drawText(QRectF(0, 0, w->width(), headerH), Qt::AlignLeft | Qt::AlignVCenter, title);

    QColor frame = pal.color(QPalette::Mid);
    painter.setPen(frame);
    painter.setBrush(pal.color(QPalette::Base));
    painter.drawRect(plot);
    frame.setAlphaF(0.4f);
    painter.setPen(frame);
    painter.drawLine(QPointF(plot.left(), plot.center().y()),
                     QPointF(plot.right(), plot.center().y()));
    return plot;
}

} // namespace

void HistoryGraph::paintEvent(QPaintEvent *) {
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);

    const QPalette pal = palette();
    const QColor accent = pal.color(QPalette::Highlight);
    const QRectF plot = paintHeaderAndFrame(painter, this, title_, caption_);

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

MultiHistoryGraph::MultiHistoryGraph(const QString &title, QWidget *parent, const QSize &minSize)
    : QWidget(parent), title_(title), minSize_(minSize) {
    setMinimumSize(minimumSizeHint());
}

void MultiHistoryGraph::push(const QVector<double> &values, const QString &caption) {
    if (history_.size() != values.size()) {
        history_.clear();
        history_.resize(values.size());
    }
    for (int i = 0; i < values.size(); ++i) {
        history_[i].append(qBound(0.0, values.at(i), 100.0));
        if (history_[i].size() > kSamples)
            history_[i].removeFirst();
    }
    caption_ = caption;
    update();
}

void MultiHistoryGraph::paintEvent(QPaintEvent *) {
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);

    const QRectF plot = paintHeaderAndFrame(painter, this, title_, caption_);
    if (history_.isEmpty())
        return;

    // Colors stepped by the golden angle stay maximally spread for any core
    // count; light themes get darker lines, dark themes brighter ones.
    const bool darkTheme = palette().color(QPalette::Window).lightnessF() < 0.5;
    const double dx = plot.width() / double(kSamples - 1);
    painter.setClipRect(plot);
    painter.setBrush(Qt::NoBrush);
    for (int s = 0; s < history_.size(); ++s) {
        const QVector<double> &series = history_.at(s);
        if (series.isEmpty())
            continue;
        QColor color = QColor::fromHsvF(float(std::fmod(s * 0.618034, 1.0)),
                                        darkTheme ? 0.55f : 0.7f,
                                        darkTheme ? 0.95f : 0.62f);
        color.setAlphaF(0.75f);
        QPainterPath line;
        for (int i = 0; i < series.size(); ++i) {
            const double x = plot.right() - dx * double(series.size() - 1 - i);
            const double y = plot.bottom() - series.at(i) / 100.0 * plot.height();
            if (i == 0)
                line.moveTo(x, y);
            else
                line.lineTo(x, y);
        }
        painter.setPen(QPen(color, 1.0));
        painter.drawPath(line);
    }
}

} // namespace ezra
