#include <QtTest>

#include "sefe.h"

class TestSefe : public QObject {
    Q_OBJECT
private slots:
    void initialDirFollowsHome() {
        qputenv("HOME", "/home/tester");
        QCOMPARE(helm::sefe::initialDir(), QStringLiteral("/home/tester"));
    }

    void windowTitleNamesTheFolder() {
        qputenv("HOME", "/home/tester");
        // Home gets the friendly label.
        QCOMPARE(helm::sefe::windowTitle(QStringLiteral("/home/tester")),
                 QStringLiteral("Home — Seahorse"));
        // Any other dir uses its base name.
        QCOMPARE(helm::sefe::windowTitle(QStringLiteral("/home/tester/Documents")),
                 QStringLiteral("Documents — Seahorse"));
        // The filesystem root has no base name → show the path.
        QCOMPARE(helm::sefe::windowTitle(QStringLiteral("/")),
                 QStringLiteral("/ — Seahorse"));
    }
};

QTEST_MAIN(TestSefe)
#include "test_sefe.moc"
