#include <QtTest>

#include "palette.h"

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

    void styleSheetGlassBar() {
        const QString qss = helm::styleSheet(false, helm::harborAccent());
        QVERIFY(qss.contains(QStringLiteral("#HelmBar")));           // the glass bar
        QVERIFY(qss.contains(QStringLiteral("Segoe UI")));           // familiar font
        QVERIFY(qss.contains(QStringLiteral("rgba(11,38,46,0.82)"))); // bar_tint (navy glass)
        // accent drives selection: Harbor #3aa6c4 → rgb(58,166,196) at 34%
        QVERIFY(qss.contains(QStringLiteral("rgba(58,166,196,0.34)")));
        // an invalid accent falls back to Harbor rather than producing an unstyled bar
        QVERIFY(helm::styleSheet(false, QColor()).contains(QStringLiteral("rgba(58,166,196")));
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
};

QTEST_MAIN(TestAppearance)
#include "test_appearance.moc"
