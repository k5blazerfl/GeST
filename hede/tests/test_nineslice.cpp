#include <QtTest>

#include "nineslice.h"

class TestNineSlice : public QObject {
    Q_OBJECT

    static helm::SliceRect find(const QList<helm::SliceRect> &v, const QRect &src) {
        for (const auto &s : v)
            if (s.src == src)
                return s;
        return {QRect(), QRect()};
    }

private slots:
    // 100x100 source, 10px insets, into a 200x300 target.
    void bordersMapCorrectly() {
        const auto v = helm::nineSliceBorder(QSize(100, 100), QMargins(10, 10, 10, 10),
                                             QRect(0, 0, 200, 300));
        QCOMPARE(v.size(), 8); // four corners + four edges, centre omitted

        // corners keep their native 10x10 size, pinned to the target corners
        QCOMPARE(find(v, QRect(0, 0, 10, 10)).dst, QRect(0, 0, 10, 10));       // TL
        QCOMPARE(find(v, QRect(90, 0, 10, 10)).dst, QRect(190, 0, 10, 10));    // TR
        QCOMPARE(find(v, QRect(0, 90, 10, 10)).dst, QRect(0, 290, 10, 10));    // BL
        QCOMPARE(find(v, QRect(90, 90, 10, 10)).dst, QRect(190, 290, 10, 10)); // BR

        // top edge stretches across the width; left edge down the height
        QCOMPARE(find(v, QRect(10, 0, 80, 10)).dst, QRect(10, 0, 180, 10));
        QCOMPARE(find(v, QRect(0, 10, 10, 80)).dst, QRect(0, 10, 10, 280));
    }

    // Asymmetric insets (l=6, t=40, r=6, b=8) — a HeDE titlebar frame.
    void asymmetricInsets() {
        const auto v = helm::nineSliceBorder(QSize(1280, 288), QMargins(6, 40, 6, 8),
                                             QRect(0, 0, 800, 500));
        // top-left corner is 6 wide x 40 tall
        QCOMPARE(find(v, QRect(0, 0, 6, 40)).dst, QRect(0, 0, 6, 40));
        // titlebar (top edge) is 40 tall, stretched across 800-6-6 = 788
        QCOMPARE(find(v, QRect(6, 0, 1268, 40)).dst, QRect(6, 0, 788, 40));
        // bottom-right corner 6x8 pinned bottom-right
        QCOMPARE(find(v, QRect(1274, 280, 6, 8)).dst, QRect(794, 492, 6, 8));
    }

    // Degenerate pieces (zero-run edges) are skipped, not emitted empty.
    void skipsDegenerate() {
        // target exactly as wide as l+r → no horizontal middle: top/bottom edges drop
        const auto v = helm::nineSliceBorder(QSize(100, 100), QMargins(10, 10, 10, 10),
                                             QRect(0, 0, 20, 300));
        for (const auto &s : v)
            QVERIFY(s.dst.width() > 0 && s.dst.height() > 0);
    }
};

QTEST_MAIN(TestNineSlice)
#include "test_nineslice.moc"
