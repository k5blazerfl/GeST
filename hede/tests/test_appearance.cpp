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
};

QTEST_MAIN(TestAppearance)
#include "test_appearance.moc"
