#include <QtTest>

#include <QSettings>
#include <QTemporaryDir>

#include "catalog.h"
#include "editor.h"
#include "layout.h"

using helm::PanelEditorModel;
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

    // ---- editor model (slice 4) ------------------------------------------
    void editorLoadReorderApplyRoundTrips() {
        QTemporaryDir dir;
        const QString path = dir.filePath(QStringLiteral("hede.conf"));
        PanelEditorModel m;
        m.loadFrom(path); // unset → default lineup
        QCOMPARE(m.applets(), helm::defaultApplets());
        m.moveItem(0, 2); // drag launcher two slots right
        QCOMPARE(m.applets().at(2), QStringLiteral("launcher"));
        QVERIFY(m.apply(path));
        QCOMPARE(PanelLayout::read(path), m.applets()); // the bar would see this
    }
    void editorAddRemoveTracksAvailable() {
        PanelEditorModel m;
        m.setApplets({QStringLiteral("launcher"), QStringLiteral("clock")});
        const QStringList avail = m.available();
        QVERIFY(avail.contains(QStringLiteral("tray")));      // not on the bar → offered
        QVERIFY(!avail.contains(QStringLiteral("launcher"))); // already on the bar → not
        QVERIFY(avail.contains(QStringLiteral("spacer")));    // gap always offered

        m.append(QStringLiteral("tray"));
        QCOMPARE(m.applets(), (QStringList{QStringLiteral("launcher"), QStringLiteral("clock"),
                                           QStringLiteral("tray")}));
        QVERIFY(!m.available().contains(QStringLiteral("tray"))); // now placed

        m.removeAt(1); // drop clock
        QCOMPARE(m.applets(),
                 (QStringList{QStringLiteral("launcher"), QStringLiteral("tray")}));
        QVERIFY(m.available().contains(QStringLiteral("clock"))); // returns to Available
    }
    void editorSpacerIsRepeatable() {
        PanelEditorModel m;
        m.setApplets({QStringLiteral("taskbar")});
        m.append(QStringLiteral("spacer"));
        m.append(QStringLiteral("spacer"));
        QCOMPARE(m.applets().count(QStringLiteral("spacer")), 2);
        QVERIFY(m.available().contains(QStringLiteral("spacer"))); // still offerable
    }
    void editorGuardsBadIndicesAndEmptyIds() {
        PanelEditorModel m;
        m.setApplets({QStringLiteral("launcher"), QStringLiteral("clock")});
        m.moveItem(-1, 0);          // out of range
        m.moveItem(0, 9);           // out of range
        m.removeAt(5);              // out of range
        m.insert(0, QString());     // empty id ignored
        QCOMPARE(m.applets(),
                 (QStringList{QStringLiteral("launcher"), QStringLiteral("clock")}));
        m.insert(1, QStringLiteral("tray"));
        QCOMPARE(m.applets(), (QStringList{QStringLiteral("launcher"), QStringLiteral("tray"),
                                           QStringLiteral("clock")}));
    }
    void editorResetToDefault() {
        PanelEditorModel m;
        m.setApplets({QStringLiteral("clock")});
        m.setEdge(QStringLiteral("top"));
        m.resetToDefault();
        QCOMPARE(m.applets(), helm::defaultApplets());
        QCOMPARE(m.edge(), QStringLiteral("bottom")); // reset restores the edge too
    }

    // ---- edge (slice 6) --------------------------------------------------
    void edgeDefaultsToBottomWhenUnset() {
        QTemporaryDir dir;
        const QString path = dir.filePath(QStringLiteral("hede.conf"));
        QCOMPARE(PanelLayout::readEdge(path), QStringLiteral("bottom"));
        // All four edges are offered (bottom/top horizontal, left/right vertical).
        const QStringList e = PanelLayout::validEdges();
        for (const char *want : {"bottom", "top", "left", "right"})
            QVERIFY(e.contains(QString::fromLatin1(want)));
    }
    void edgeWriteReadRoundTripsAllFour() {
        QTemporaryDir dir;
        const QString path = dir.filePath(QStringLiteral("hede.conf"));
        for (const QString &edge : PanelLayout::validEdges()) {
            QVERIFY(PanelLayout::writeEdge(path, edge));
            QCOMPARE(PanelLayout::readEdge(path), edge);
        }
    }
    void edgeNormalisesCaseAndRejectsGarbage() {
        QTemporaryDir dir;
        const QString path = dir.filePath(QStringLiteral("hede.conf"));
        QVERIFY(PanelLayout::writeEdge(path, QStringLiteral("  TOP ")));
        QCOMPARE(PanelLayout::readEdge(path), QStringLiteral("top")); // trimmed + lowered
        // A bad value written directly to the INI reads back as the default.
        {
            QSettings s(path, QSettings::IniFormat);
            s.setValue(QStringLiteral("panel/edge"), QStringLiteral("sideways"));
        }
        QCOMPARE(PanelLayout::readEdge(path), QStringLiteral("bottom"));
    }
    void editorEdgeLoadsSetsAppliesAndValidates() {
        QTemporaryDir dir;
        const QString path = dir.filePath(QStringLiteral("hede.conf"));
        PanelEditorModel m;
        m.loadFrom(path);
        QCOMPARE(m.edge(), QStringLiteral("bottom")); // default when unset
        m.setEdge(QStringLiteral("top"));
        QCOMPARE(m.edge(), QStringLiteral("top"));
        QVERIFY(m.apply(path));
        QCOMPARE(PanelLayout::readEdge(path), QStringLiteral("top")); // the bar would re-anchor
        m.setEdge(QStringLiteral("garbage"));
        QCOMPARE(m.edge(), QStringLiteral("bottom")); // invalid snaps back to default
    }
};

QTEST_MAIN(TestBarnacle)
#include "test_barnacle.moc"
