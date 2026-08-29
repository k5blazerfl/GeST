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

    explicit HistoryGraph(const QString &title, Scale scale, QWidget *parent = nullptr);

    // value: percent (0–100) or a raw rate, per the scale mode.
    // caption: the current-value text shown in the corner ("37 %", "1.2 MB/s").
    void push(double value, const QString &caption);

    QSize minimumSizeHint() const override { return {220, 120}; }

protected:
    void paintEvent(QPaintEvent *event) override;

private:
    QString title_;
    QString caption_;
    Scale scale_;
    QVector<double> history_; // ring, capped at kSamples
};

} // namespace ezra
