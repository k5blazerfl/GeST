#include <QtTest>

#include <QSettings>
#include <QTemporaryDir>

#include "catalog.h"
#include "layout.h"

using helm::PanelLayout;

class TestBarnacle : public QObject {
    Q_OBJECT
  private slots:
    // ---- catalog ---------------------------------------------------------
    void catalogHasLabelledEntries() {
        const auto &cat = helm::appletCatalog();
        QVERIFY(!cat.isEmpty());
        for (const helm::AppletInfo &a : cat) {
            QVERIFY2(!a.id.isEmpty(), "every applet has an id");
            QVERIFY2(!a.label.isEmpty(), qPrintable(QStringLiteral("applet %1 has a label").arg(a.id)));
            // The id is the normalised token: lower-case, no surrounding space.
            QCOMPARE(a.id, a.id.trimmed().toLower());
        }
    }
    void defaultAppletsAreTheDefaultEntriesInOrder() {
        const QStringList def = helm::defaultApplets();
        // Mirrors the historical hard-coded bar order.
        const QStringList expected = {
            QStringLiteral("launcher"),   QStringLiteral("taskbar"),
            QStringLiteral("mpris"),      QStringLiteral("update"),
            QStringLiteral("network"),    QStringLiteral("battery"),
            QStringLiteral("brightness"), QStringLiteral("volume"),
            QStringLiteral("dnd"),        QStringLiteral("tray"),
            QStringLiteral("clock"),
        };
        QCOMPARE(def, expected);
        // spacer exists but is not part of the default lineup.
        QVERIFY(helm::isKnownApplet(QStringLiteral("spacer")));
        QVERIFY(!def.contains(QStringLiteral("spacer")));
    }
    void lookupsAndAliases() {
        QVERIFY(helm::isKnownApplet(QStringLiteral("clock")));
        QVERIFY(!helm::isKnownApplet(QStringLiteral("nonsense")));
        QCOMPARE(helm::findApplet(QStringLiteral("clock"))->kind, helm::AppletKind::Widget);
        QCOMPARE(helm::findApplet(QStringLiteral("spacer"))->kind, helm::AppletKind::Stretch);
        // `stretch` is a recognised alias resolving to the canonical `spacer`.
        QVERIFY(helm::isKnownApplet(QStringLiteral("stretch")));
        QCOMPARE(helm::findApplet(QStringLiteral("stretch"))->id, QStringLiteral("spacer"));
    }

    // ---- parse -----------------------------------------------------------
    void parseToleratesWhitespaceCaseAndEmpties() {
        QCOMPARE(PanelLayout::parse(QStringLiteral("  Launcher , ,TASKBAR,  Clock ,")),
                 (QStringList{QStringLiteral("launcher"), QStringLiteral("taskbar"),
                              QStringLiteral("clock")}));
        QCOMPARE(PanelLayout::parse(QString()), QStringList());
    }

    // ---- read ------------------------------------------------------------
    void readDefaultsWhenUnset() {
        QTemporaryDir dir;
        const QString path = dir.filePath(QStringLiteral("hede.conf"));
        QCOMPARE(PanelLayout::read(path), helm::defaultApplets());
    }
    void readEmptyValueFallsBackToDefault() {
        QTemporaryDir dir;
        const QString path = dir.filePath(QStringLiteral("hede.conf"));
        {
            QSettings s(path, QSettings::IniFormat);
            s.setValue(QStringLiteral("panel/applets"), QStringLiteral("   "));
        }
        QCOMPARE(PanelLayout::read(path), helm::defaultApplets());
    }
    void readHonoursCustomOrder() {
        QTemporaryDir dir;
        const QString path = dir.filePath(QStringLiteral("hede.conf"));
        {
            QSettings s(path, QSettings::IniFormat);
            s.setValue(QStringLiteral("panel/applets"),
                       QStringLiteral("clock, spacer, launcher"));
        }
        QCOMPARE(PanelLayout::read(path), (QStringList{QStringLiteral("clock"),
                                                       QStringLiteral("spacer"),
                                                       QStringLiteral("launcher")}));
    }

    // ---- write -----------------------------------------------------------
    void writeReadRoundTrips() {
        QTemporaryDir dir;
        const QString path = dir.filePath(QStringLiteral("hede.conf"));
        const QStringList wanted = {QStringLiteral("launcher"), QStringLiteral("taskbar"),
                                    QStringLiteral("clock")};
        QVERIFY(PanelLayout::write(path, wanted));
        QCOMPARE(PanelLayout::read(path), wanted);
    }
    void writeEmptyClearsToDefault() {
        QTemporaryDir dir;
        const QString path = dir.filePath(QStringLiteral("hede.conf"));
        QVERIFY(PanelLayout::write(path, {QStringLiteral("clock")}));
        QCOMPARE(PanelLayout::read(path), QStringList{QStringLiteral("clock")});
        // An empty write clears the key → the bar falls back to the default lineup.
        QVERIFY(PanelLayout::write(path, {}));
        QCOMPARE(PanelLayout::read(path), helm::defaultApplets());
    }
    void readReflectsExternalRewrite() {
        // The editor writes; a fresh read (as the panel's live-reload does) must
        // see it — QSettings does not serve stale cache.
        QTemporaryDir dir;
        const QString path = dir.filePath(QStringLiteral("hede.conf"));
        QVERIFY(PanelLayout::write(path, {QStringLiteral("launcher"), QStringLiteral("clock")}));
        QCOMPARE(PanelLayout::read(path),
                 (QStringList{QStringLiteral("launcher"), QStringLiteral("clock")}));
        QVERIFY(PanelLayout::write(path, {QStringLiteral("clock"), QStringLiteral("tray"),
                                          QStringLiteral("launcher")}));
        QCOMPARE(PanelLayout::read(path),
                 (QStringList{QStringLiteral("clock"), QStringLiteral("tray"),
                              QStringLiteral("launcher")}));
    }
};

QTEST_MAIN(TestBarnacle)
#include "test_barnacle.moc"
