#include "palette.h"

#include "config.h"

#include <QApplication>

namespace helm {

QColor contrastText(const QColor &bg) {
    const double lum = 0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue();
    return lum > 140 ? QColor(Qt::black) : QColor(Qt::white);
}

QPalette buildPalette(bool dark, const QColor &accent) {
    QPalette p; // default = light
    if (dark) {
        const QColor window(0x2b, 0x2b, 0x2b), base(0x1e, 0x1e, 0x1e), alt(0x24, 0x24, 0x24),
            text(0xe6, 0xe6, 0xe6), button(0x32, 0x32, 0x32), disabled(0x7f, 0x7f, 0x7f);
        p.setColor(QPalette::Window, window);
        p.setColor(QPalette::WindowText, text);
        p.setColor(QPalette::Base, base);
        p.setColor(QPalette::AlternateBase, alt);
        p.setColor(QPalette::Text, text);
        p.setColor(QPalette::Button, button);
        p.setColor(QPalette::ButtonText, text);
        p.setColor(QPalette::ToolTipBase, window);
        p.setColor(QPalette::ToolTipText, text);
        p.setColor(QPalette::PlaceholderText, disabled);
        p.setColor(QPalette::Disabled, QPalette::Text, disabled);
        p.setColor(QPalette::Disabled, QPalette::WindowText, disabled);
        p.setColor(QPalette::Disabled, QPalette::ButtonText, disabled);
    }
    if (accent.isValid()) {
        p.setColor(QPalette::Highlight, accent);
        p.setColor(QPalette::HighlightedText, contrastText(accent));
    }
    return p;
}

void applyAppearance() {
    const Config cfg;
    const bool dark = cfg.string(QStringLiteral("appearance/dark")) == QLatin1String("true");
    const QColor accent(cfg.string(QStringLiteral("appearance/accent")));
    if (!dark && !accent.isValid())
        return; // nothing themed → keep the native look

    if (auto *app = qobject_cast<QApplication *>(QApplication::instance()))
        app->setStyle(QStringLiteral("Fusion")); // honours a custom palette
    QGuiApplication::setPalette(buildPalette(dark, accent));
}

} // namespace helm
