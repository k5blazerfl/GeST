// A scrolling history graph for the Performance tab: 60 samples, newest on
// the right, drawn from the widget palette (accent line over a translucent
// fill) so it re-tints with the Helm appearance like every other surface.
// Percent graphs are fixed 0–100; rate graphs autoscale to the window peak.
#pragma once

#include <QVector>
#include <QWidget>

namespace ezra {

class HistoryGraph : public QWidget {
    Q_OBJECT
public:
    enum Scale { Percent, AutoScale };

    // minSize shrinks the per-core thumbnails; the default suits a full tile.
    explicit HistoryGraph(const QString &title, Scale scale, QWidget *parent = nullptr,
                          const QSize &minSize = {220, 120});

    // value: percent (0–100) or a raw rate, per the scale mode.
    // caption: the current-value text shown in the corner ("37 %", "1.2 MB/s").
    void push(double value, const QString &caption);

    QSize minimumSizeHint() const override { return minSize_; }

protected:
    void paintEvent(QPaintEvent *event) override;

private:
    QString title_;
    QString caption_;
    Scale scale_;
    QSize minSize_;
    QVector<double> history_; // ring, capped at kSamples
};

// All logical processors as one graph: a thin 0–100 trace per core, colors
// stepped around the hue wheel by the golden angle so any core count stays
// as distinct as it can be, semi-transparent so pile-ups read as density.
class MultiHistoryGraph : public QWidget {
    Q_OBJECT
public:
    explicit MultiHistoryGraph(const QString &title, QWidget *parent = nullptr,
                               const QSize &minSize = {220, 120});

    // One percent value per series; a changed series count resets history.
    void push(const QVector<double> &values, const QString &caption);

    QSize minimumSizeHint() const override { return minSize_; }

protected:
    void paintEvent(QPaintEvent *event) override;

private:
    QString title_;
    QString caption_;
    QSize minSize_;
    QVector<QVector<double>> history_; // per series, each capped at kSamples
};

} // namespace ezra
