#include <QtTest>

#include <QDir>
#include <QFile>
#include <QStandardPaths>

#include "identitymap.h"

using helm::IdentityResolver;
using helm::WindowIdentity;

// Verifies the read half of the Customs identity spine: normalization parity with
// gest/core/customs/identity.py::normalize, and app_id → .desktop icon+name
// resolution (including NoDisplay handler entries like gangway-rdp-handler).
class TestIdentityMap : public QObject {
    Q_OBJECT
  private:
    static void writeFile(const QString &path, const QString &text) {
        QDir().mkpath(QFileInfo(path).absolutePath());
        QFile f(path);
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Truncate));
        f.write(text.toUtf8());
    }

    static QString appsDir() {
        return QStandardPaths::writableLocation(QStandardPaths::ApplicationsLocation);
    }

  private slots:
    void initTestCase() {
        QStandardPaths::setTestModeEnabled(true); // redirect XDG dirs into a temp tree
    }

    void normalizeMatchesPythonWriter() {
        // trim + lowercase
        QCOMPARE(IdentityResolver::normalizeKey(QStringLiteral("  Org.FreeRDP.Client ")),
                 QStringLiteral("org.freerdp.client")); // dots kept (reverse-DNS)
        // X11 WM_CLASS: take the instance before the NUL
        const QString wmclass = QStringLiteral("Instance") + QChar(u'\0') + QStringLiteral("Class");
        QCOMPARE(IdentityResolver::normalizeKey(wmclass), QStringLiteral("instance"));
        QCOMPARE(IdentityResolver::normalizeKey(QStringLiteral("Excel")), QStringLiteral("excel"));
    }

    void resolvesHandlerAndDrydock() {
        // The map the Python writer produces (keys already normalized).
        writeFile(IdentityResolver::identityPath(),
                  QStringLiteral("{\"version\":1,\"map\":{"
                                 "\"org.freerdp.client\":\"gangway-rdp-handler\","
                                 "\"freerdp\":\"gangway-rdp-handler\","
                                 "\"excel\":\"drydock-office-excel\"}}"));
        // A NoDisplay handler entry must still resolve (parsed by id, not scanned).
        writeFile(appsDir() + QStringLiteral("/gangway-rdp-handler.desktop"),
                  QStringLiteral("[Desktop Entry]\nType=Application\nName=Remote Desktop (.rdp)\n"
                                 "Icon=gangway\nExec=gangway-rdp-open %u\nNoDisplay=true\n"));
        writeFile(appsDir() + QStringLiteral("/drydock-office-excel.desktop"),
                  QStringLiteral("[Desktop Entry]\nType=Application\nName=Excel\nIcon=excel\n"
                                 "Exec=drydock-run office excel\n"));

        IdentityResolver r;

        const WindowIdentity g = r.resolve(QStringLiteral("org.freerdp.client"));
        QVERIFY(g.found);
        QCOMPARE(g.name, QStringLiteral("Remote Desktop (.rdp)"));
        QCOMPARE(g.iconName, QStringLiteral("gangway"));

        // Normalization applies on lookup too (uppercase + surrounding space).
        QVERIFY(r.resolve(QStringLiteral("  ORG.FreeRDP.Client ")).found);

        const WindowIdentity d = r.resolve(QStringLiteral("excel"));
        QVERIFY(d.found);
        QCOMPARE(d.name, QStringLiteral("Excel"));
        QCOMPARE(d.iconName, QStringLiteral("excel"));

        // An unmapped native app falls through (taskbar keeps its text label).
        QVERIFY(!r.resolve(QStringLiteral("org.mozilla.firefox")).found);
    }

    void reloadPicksUpNewMappings() {
        writeFile(IdentityResolver::identityPath(),
                  QStringLiteral("{\"version\":1,\"map\":{}}"));
        IdentityResolver r;
        QVERIFY(!r.resolve(QStringLiteral("org.freerdp.client")).found);

        writeFile(IdentityResolver::identityPath(),
                  QStringLiteral("{\"version\":1,\"map\":{"
                                 "\"org.freerdp.client\":\"gangway-rdp-handler\"}}"));
        writeFile(appsDir() + QStringLiteral("/gangway-rdp-handler.desktop"),
                  QStringLiteral("[Desktop Entry]\nType=Application\nName=Remote Desktop (.rdp)\n"
                                 "Icon=gangway\nExec=gangway-rdp-open %u\nNoDisplay=true\n"));
        r.reload();
        QVERIFY(r.resolve(QStringLiteral("org.freerdp.client")).found);
    }

    void missingFileIsEmptyNotCrash() {
        QFile::remove(IdentityResolver::identityPath());
        IdentityResolver r; // reload() on a missing file → empty map, no throw
        QVERIFY(!r.resolve(QStringLiteral("org.freerdp.client")).found);
    }
};

QTEST_MAIN(TestIdentityMap)
#include "test_identitymap.moc"
