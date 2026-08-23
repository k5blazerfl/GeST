#include <QtTest>

#include "categories.h"

class TestCategories : public QObject {
    Q_OBJECT
private slots:
    void mapsMainCategories() {
        QCOMPARE(helm::sectionForCategories({"Network", "WebBrowser"}),
                 QStringLiteral("Internet"));
        QCOMPARE(helm::sectionForCategories({"AudioVideo", "Player"}),
                 QStringLiteral("Multimedia"));
        QCOMPARE(helm::sectionForCategories({"Audio"}), QStringLiteral("Multimedia"));
        QCOMPARE(helm::sectionForCategories({"Development", "IDE"}),
                 QStringLiteral("Development"));
        QCOMPARE(helm::sectionForCategories({"Utility", "TextEditor"}),
                 QStringLiteral("Accessories"));
        QCOMPARE(helm::sectionForCategories({"Game"}), QStringLiteral("Games"));
    }

    void unrecognisedFallsToOther() {
        QCOMPARE(helm::sectionForCategories({"WebBrowser", "Qt"}), QStringLiteral("Other"));
        QCOMPARE(helm::sectionForCategories({}), QStringLiteral("Other"));
    }

    void priorityFunctionalBeatsGenericBucket() {
        // An app tagged both a functional group and a generic bucket lands in the
        // more specific one, regardless of order in the list.
        QCOMPARE(helm::sectionForCategories({"Utility", "System"}),
                 QStringLiteral("System")); // System before Utility in the table
        QCOMPARE(helm::sectionForCategories({"System", "Settings"}),
                 QStringLiteral("Settings")); // Settings before System
        QCOMPARE(helm::sectionForCategories({"Graphics", "Utility"}),
                 QStringLiteral("Graphics")); // functional group wins over Accessories
    }

    void caseSensitiveExactMatch() {
        // Spec categories are PascalCase; a lowercase tag must not match.
        QCOMPARE(helm::sectionForCategories({"network"}), QStringLiteral("Other"));
    }
};

QTEST_MAIN(TestCategories)
#include "test_categories.moc"
