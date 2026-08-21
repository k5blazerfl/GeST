#include "palette.h"

#include "config.h"
#include "theme.h"
#include "world.h"

#include <QApplication>
#include <QFileInfo>
#include <QFileSystemWatcher>
#include <QPainter>
#include <QStyle>
#include <QStyleOption>
#include <QTimer>
#include <QWidget>

namespace helm {

void paintStyledSurface(QWidget *w) {
    // The documented Qt idiom for honouring a QSS background/border on a custom
    // QWidget — required here because WA_TranslucentBackground suppresses the
    // default styled fill on a top-level, leaving the glass surface transparent.
    QStyleOption opt;
    opt.initFrom(w);
    QPainter p(w);
    w->style()->drawPrimitive(QStyle::PE_Widget, &opt, &p, w);
}

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

QColor effectiveAccent(const Config &cfg) {
    // 1) an explicit [appearance] accent (the user's helm-theme choice) wins.
    const QColor explicitAccent(cfg.string(QStringLiteral("appearance/accent")));
    if (explicitAccent.isValid())
        return explicitAccent;
    // 2) the active world's accent — switching worlds re-tints the shell.
    const World world = loadWorld(cfg.string(QStringLiteral("world/id"), QStringLiteral("harbor")));
    const QColor worldAccent(world.accent);
    if (worldAccent.isValid())
        return worldAccent;
    // 3) the built-in Harbor teal.
    return harborAccent();
}

// The effective light/dark for the shell palette: the [appearance] `mode` knob
// (dark/light/auto), falling back to the legacy `dark` bool. `auto` = follow-the-
// sun, using [appearance] latitude (default mid-latitude). Mirrors the labwc/GTK
// resolution in helm::applyThemeFromWorld so every surface agrees.
static bool configDark(const Config &cfg) {
    const bool legacy = cfg.string(QStringLiteral("appearance/dark")) == QLatin1String("true");
    bool ok = false;
    const double lat = cfg.string(QStringLiteral("appearance/latitude")).toDouble(&ok);
    return resolveDark(cfg.string(QStringLiteral("appearance/mode")), legacy, ok ? lat : 40.0);
}

void applyAppearance() {
    const Config cfg;
    const bool dark = configDark(cfg);
    const QColor accent = effectiveAccent(cfg);

    if (auto *app = qobject_cast<QApplication *>(QApplication::instance())) {
        app->setStyle(QStringLiteral("Fusion")); // honours a custom palette
        app->setStyleSheet(styleSheet(dark, accent));
    }
    QGuiApplication::setPalette(buildPalette(dark, accent));
}

void watchAppearance() {
    QCoreApplication *app = QCoreApplication::instance();
    if (!app)
        return;
    const QString path = Config().path();
    auto *watcher = new QFileSystemWatcher(app);
    // Watch the directory too: QSettings rewrites via a temp file + rename, which
    // drops the per-file watch, so we re-arm on every signal.
    watcher->addPath(QFileInfo(path).absolutePath());
    if (QFileInfo::exists(path))
        watcher->addPath(path);

    auto reapply = [watcher, path]() {
        if (!watcher->files().contains(path) && QFileInfo::exists(path))
            watcher->addPath(path); // re-arm after an atomic rewrite
        applyAppearance();
    };
    QObject::connect(watcher, &QFileSystemWatcher::fileChanged, app, reapply);
    QObject::connect(watcher, &QFileSystemWatcher::directoryChanged, app, reapply);

    // Follow-the-sun: in `mode = auto` the dark flag turns on the clock, not on a
    // config write, so poll on a slow timer and re-apply only when the resolved
    // value actually flips (sunrise/sunset). A cheap no-op for fixed dark/light.
    auto *sun = new QTimer(app);
    sun->setInterval(10 * 60 * 1000); // 10 min — fine granularity near twilight
    QObject::connect(sun, &QTimer::timeout, app, [] {
        static int last = -1;
        const int dark = configDark(Config()) ? 1 : 0;
        if (dark != last) {
            last = dark;
            applyAppearance();
        }
    });
    sun->start();
}

} // namespace helm
