#include <QtTest>

#include <QDir>
#include <QSettings>
#include <QTemporaryDir>

#include "config.h"
#include "palette.h"

// Write a minimal world with the given accent under <worldsDir>/<id>/theme.yaml.
static void writeWorld(const QString &worldsDir, const QString &id, const QString &accent) {
    const QString dir = QDir(worldsDir).filePath(id);
    QDir().mkpath(dir);
    QFile y(QDir(dir).filePath(QStringLiteral("theme.yaml")));
    if (y.open(QIODevice::WriteOnly)) {
        y.write(QStringLiteral("id: %1\naccent: '%2'\n").arg(id, accent).toUtf8());
        y.close();
    }
}

class TestAppearance : public QObject {
    Q_OBJECT
private slots:
    void contrast() {
        QCOMPARE(helm::contrastText(QColor(Qt::white)), QColor(Qt::black));
        QCOMPARE(helm::contrastText(QColor(QStringLiteral("#0a1633"))), QColor(Qt::white)); // navy
        QCOMPARE(helm::contrastText(QColor(QStringLiteral("#33d6c8"))), QColor(Qt::black)); // teal
    }

    void darkPaletteWithAccent() {
        const QColor accent(QStringLiteral("#33d6c8"));
        const QPalette p = helm::buildPalette(true, accent);
        QCOMPARE(p.color(QPalette::Highlight), accent);
        QCOMPARE(p.color(QPalette::HighlightedText), QColor(Qt::black));
        QVERIFY(p.color(QPalette::Window).value() < 128); // actually dark
        QVERIFY(p.color(QPalette::WindowText).value() > 128);
    }

    void lightAccentOnly() {
        const QColor accent(QStringLiteral("#127e75"));
        const QPalette p = helm::buildPalette(false, accent);
        QCOMPARE(p.color(QPalette::Highlight), accent);
        QVERIFY(p.color(QPalette::Window).value() > 128); // still light
    }

    void harborDefault() {
        QCOMPARE(helm::harborAccent(), QColor(QStringLiteral("#3aa6c4")));
    }

    // An explicit [appearance] accent always wins, even with a world present.
    void effectiveAccentPrefersExplicit() {
        QTemporaryDir worlds;
        writeWorld(worlds.path(), QStringLiteral("harbor"), QStringLiteral("#aabbcc"));
        qputenv("HELM_WORLDS_DIR", worlds.path().toLocal8Bit());
        QTemporaryDir cfgdir;
        const QString path = cfgdir.filePath(QStringLiteral("hede.conf"));
        {
            QSettings s(path, QSettings::IniFormat);
            s.setValue(QStringLiteral("appearance/accent"), QStringLiteral("#123456"));
        }
        QCOMPARE(helm::effectiveAccent(helm::Config(path)), QColor(QStringLiteral("#123456")));
        qunsetenv("HELM_WORLDS_DIR");
    }

    // No explicit accent → the active world's accent tints the shell.
    void effectiveAccentFromWorld() {
        QTemporaryDir worlds;
        writeWorld(worlds.path(), QStringLiteral("harbor"), QStringLiteral("#3aa6c4"));
        writeWorld(worlds.path(), QStringLiteral("emberforge"), QStringLiteral("#e8853a"));
        qputenv("HELM_WORLDS_DIR", worlds.path().toLocal8Bit());
        QTemporaryDir cfgdir;
        const QString path = cfgdir.filePath(QStringLiteral("hede.conf"));
        // default world (harbor)
        QCOMPARE(helm::effectiveAccent(helm::Config(path)), QColor(QStringLiteral("#3aa6c4")));
        // switching worlds re-tints
        {
            QSettings s(path, QSettings::IniFormat);
            s.setValue(QStringLiteral("world/id"), QStringLiteral("emberforge"));
        }
        QCOMPARE(helm::effectiveAccent(helm::Config(path)), QColor(QStringLiteral("#e8853a")));
        qunsetenv("HELM_WORLDS_DIR");
    }

    // No explicit accent and no world resolvable → built-in Harbor teal.
    void effectiveAccentFallsBackToHarbor() {
        QTemporaryDir empty;
        qputenv("HELM_WORLDS_DIR", empty.path().toLocal8Bit());
        QTemporaryDir cfgdir;
        QCOMPARE(helm::effectiveAccent(helm::Config(cfgdir.filePath(QStringLiteral("hede.conf")))),
                 helm::harborAccent());
        qunsetenv("HELM_WORLDS_DIR");
    }

    void styleSheetGlassBar() {
        const QString qss = helm::styleSheet(false, helm::harborAccent());
        QVERIFY(qss.contains(QStringLiteral("#HelmBar"))); // the glass bar
        QVERIFY(qss.contains(QStringLiteral("Segoe UI"))); // familiar font
        // bar_tint is the world-derived deep glass, at 82%.
        const QColor g = helm::barTint(helm::harborAccent());
        const QString bar =
            QStringLiteral("rgba(%1,%2,%3,0.82)").arg(g.red()).arg(g.green()).arg(g.blue());
        QVERIFY2(qss.contains(bar), qPrintable(bar));
        // accent drives selection: Harbor #3aa6c4 → rgb(58,166,196) at 34%
        QVERIFY(qss.contains(QStringLiteral("rgba(58,166,196,0.34)")));
        // an invalid accent falls back to Harbor rather than producing an unstyled bar
        QVERIFY(helm::styleSheet(false, QColor()).contains(QStringLiteral("rgba(58,166,196")));
    }

    // The glass tint tracks the accent's hue and stays deep/dark in every world.
    void barTintTracksHue() {
        const QColor cool = helm::barTint(QColor(QStringLiteral("#3aa6c4"))); // Harbor teal
        const QColor warm = helm::barTint(QColor(QStringLiteral("#e8853a"))); // Emberforge
        QVERIFY(cool.blue() > cool.red());  // cool accent → blue-leaning glass
        QVERIFY(warm.red() > warm.blue());  // warm accent → red-leaning glass
        QVERIFY(cool.value() < 80 && warm.value() < 80); // both deep
        // a truly achromatic accent (hsvHue -1) falls back to the Harbor hue,
        // so the glass is tinted, never grey.
        QCOMPARE(helm::barTint(QColor(128, 128, 128)).hsvHue(), helm::harborAccent().hsvHue());
    }

    void barGlyphAndStartTile() {
        QCOMPARE(helm::barGlyphColor(), QColor(QStringLiteral("#eaf1f3")));
        const QString qss = helm::styleSheet(false, helm::harborAccent());
        QVERIFY(qss.contains(QStringLiteral("#HelmStart")));  // the ⎈ Start tile rule
        QVERIFY(qss.contains(QStringLiteral("#eaf1f3")));     // glyph colour wired into the QSS
    }

    void tintedIconFallback() {
        // A bogus theme name yields a null icon (graceful) rather than crashing.
        QVERIFY(helm::tintedIcon(QStringLiteral("no-such-icon-zzz-000"), helm::barGlyphColor(),
                                 QSize(18, 18))
                    .isNull());
    }

    void acrylicPullout() {
        const QString qss = helm::styleSheet(false, helm::harborAccent());
        QVERIFY(qss.contains(QStringLiteral("#HelmPullout")));
        QVERIFY(qss.contains(QStringLiteral("border-bottom: none")));        // flat bottom
        QVERIFY(qss.contains(QStringLiteral("border-top-left-radius: 7px"))); // top corners only
    }

    void acrylicToast() {
        const QString qss = helm::styleSheet(false, helm::harborAccent());
        QVERIFY(qss.contains(QStringLiteral("#HelmToast")));
        // the accent spine down the left edge (Harbor teal)
        QVERIFY(qss.contains(QStringLiteral("border-left: 3px solid #3aa6c4")));
    }

    // App chrome (SeFE) wears the world glass: menu bar, toolbar, address field,
    // Places pane and status bar are tinted, scoped to #HelmAppWindow so the shell
    // and plainer Qt apps are untouched. "The chrome is the world."
    void appChromeGlass() {
        const QString qss = helm::styleSheet(false, helm::harborAccent());
        // Each chrome surface is scoped to the app object name.
        for (const QString &sel : {QStringLiteral("#HelmAppWindow QMenuBar"),
                                   QStringLiteral("#HelmAppWindow QToolBar"),
                                   QStringLiteral("#HelmAppWindow QStatusBar"),
                                   QStringLiteral("#HelmAddressBar"),
                                   QStringLiteral("#HelmAppPlaces")})
            QVERIFY2(qss.contains(sel), qPrintable(sel));
        // The bars carry the world glass tint (same deep glass as #HelmBar, 82%).
        const QColor g = helm::barTint(helm::harborAccent());
        const QString bar =
            QStringLiteral("rgba(%1,%2,%3,0.82)").arg(g.red()).arg(g.green()).arg(g.blue());
        QVERIFY(qss.contains(QStringLiteral("#HelmAppWindow QMenuBar { background: %1").arg(bar)));
        // The address field is a SOLID recessed well (opaque) — a translucent bg on
        // the custom AddressBar widget would composite over white, so it must not be.
        QVERIFY(qss.contains(
            QStringLiteral("#HelmAddressBar { background: %1").arg(helm::barTint(helm::harborAccent()).darker(118).name())));
        // Glyph text on the chrome is the light bar glyph colour.
        QVERIFY(qss.contains(QStringLiteral("#HelmAppWindow QToolBar QToolButton { color: %1")
                                 .arg(helm::barGlyphColor().name())));
    }
};

QTEST_MAIN(TestAppearance)
#include "test_appearance.moc"
