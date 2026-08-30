// helm-apps autostart engine: ShowIn gating, user-shadows-system, and the
// enable/disable toggle roundtrip against real files in temp dirs.
#include "autostart.h"

#include <QTemporaryDir>
#include <QtTest>

using namespace helm;

namespace {

void writeFile(const QString &path, const QByteArray &text) {
    QFile f(path);
    QVERIFY2(f.open(QIODevice::WriteOnly | QIODevice::Text), qPrintable(path));
    f.write(text);
}

} // namespace

class TestAutostart : public QObject {
    Q_OBJECT
private slots:
    void shownIn();
    void scanShadowingAndGating();
    void disableSystemEntryWritesStub();
    void enableRemovesStub();
    void disableUserEntryInPlace();
};

void TestAutostart::shownIn() {
    DesktopEntry e = parseDesktopEntry(QStringLiteral(
        "[Desktop Entry]\nType=Application\nName=A\nExec=a\nOnlyShowIn=HeDE;KDE;\n"));
    QVERIFY(e.shownIn(QStringLiteral("HeDE")));
    QVERIFY(!e.shownIn(QStringLiteral("GNOME")));

    e = parseDesktopEntry(QStringLiteral(
        "[Desktop Entry]\nType=Application\nName=B\nExec=b\nNotShowIn=HeDE;\n"));
    QVERIFY(!e.shownIn(QStringLiteral("HeDE")));
    QVERIFY(e.shownIn(QStringLiteral("KDE")));

    e = parseDesktopEntry(QStringLiteral("[Desktop Entry]\nType=Application\nName=C\nExec=c\n"));
    QVERIFY(e.shownIn(QStringLiteral("HeDE")));
}

void TestAutostart::scanShadowingAndGating() {
    QTemporaryDir user, system;
    writeFile(system.filePath(QStringLiteral("both.desktop")),
              "[Desktop Entry]\nType=Application\nName=System both\nExec=sys-both\n");
    writeFile(system.filePath(QStringLiteral("sysonly.desktop")),
              "[Desktop Entry]\nType=Application\nName=Sys only\nExec=sys-only\n");
    writeFile(system.filePath(QStringLiteral("kdeonly.desktop")),
              "[Desktop Entry]\nType=Application\nName=KDE only\nExec=k\nOnlyShowIn=KDE;\n");
    writeFile(user.filePath(QStringLiteral("both.desktop")),
              "[Desktop Entry]\nType=Application\nName=User both\nExec=user-both\n");
    writeFile(user.filePath(QStringLiteral("hidden.desktop")),
              "[Desktop Entry]\nType=Application\nName=Hidden one\nExec=h\nHidden=true\n");

    const QVector<AutostartEntry> entries =
        scanAutostart({user.path(), system.path()}, QStringLiteral("HeDE"));
    QCOMPARE(entries.size(), 3); // both (user wins), hidden, sysonly — kdeonly gated out

    QHash<QString, AutostartEntry> byId;
    for (const AutostartEntry &a : entries)
        byId.insert(a.entry.id, a);
    QCOMPARE(byId.value(QStringLiteral("both")).entry.name, QStringLiteral("User both"));
    QVERIFY(!byId.value(QStringLiteral("both")).system);
    QVERIFY(byId.value(QStringLiteral("sysonly")).system);
    QVERIFY(byId.value(QStringLiteral("sysonly")).enabled);
    QVERIFY(!byId.value(QStringLiteral("hidden")).enabled);
    QVERIFY(!byId.contains(QStringLiteral("kdeonly")));
}

void TestAutostart::disableSystemEntryWritesStub() {
    QTemporaryDir user, system;
    writeFile(system.filePath(QStringLiteral("svc.desktop")),
              "[Desktop Entry]\nType=Application\nName=Svc\nExec=svc\n");

    QVector<AutostartEntry> entries =
        scanAutostart({user.path(), system.path()}, QStringLiteral("HeDE"));
    QCOMPARE(entries.size(), 1);
    QVERIFY(setAutostartEnabled(entries.first(), false, user.path()));

    entries = scanAutostart({user.path(), system.path()}, QStringLiteral("HeDE"));
    QCOMPARE(entries.size(), 1);
    QVERIFY(!entries.first().enabled); // the user stub now shadows the system entry
    QVERIFY(!entries.first().system);
    // The system file itself was never touched.
    QFile sys(system.filePath(QStringLiteral("svc.desktop")));
    QVERIFY(sys.open(QIODevice::ReadOnly));
    QVERIFY(!sys.readAll().contains("Hidden"));
}

void TestAutostart::enableRemovesStub() {
    QTemporaryDir user, system;
    writeFile(system.filePath(QStringLiteral("svc.desktop")),
              "[Desktop Entry]\nType=Application\nName=Svc\nExec=svc\n");
    writeFile(user.filePath(QStringLiteral("svc.desktop")),
              "[Desktop Entry]\nHidden=true\n");

    QVector<AutostartEntry> entries =
        scanAutostart({user.path(), system.path()}, QStringLiteral("HeDE"));
    QVERIFY(!entries.first().enabled);
    QVERIFY(setAutostartEnabled(entries.first(), true, user.path()));

    QVERIFY(!QFile::exists(user.filePath(QStringLiteral("svc.desktop")))); // stub gone
    entries = scanAutostart({user.path(), system.path()}, QStringLiteral("HeDE"));
    QVERIFY(entries.first().enabled);
    QVERIFY(entries.first().system); // the system entry shows through again
}

void TestAutostart::disableUserEntryInPlace() {
    QTemporaryDir user;
    writeFile(user.filePath(QStringLiteral("mine.desktop")),
              "[Desktop Entry]\nType=Application\nName=Mine\nExec=mine --flag\n");

    QVector<AutostartEntry> entries = scanAutostart({user.path()}, QStringLiteral("HeDE"));
    QVERIFY(setAutostartEnabled(entries.first(), false, user.path()));
    entries = scanAutostart({user.path()}, QStringLiteral("HeDE"));
    QVERIFY(!entries.first().enabled);
    QCOMPARE(entries.first().entry.exec, QStringLiteral("mine --flag")); // Exec survived

    QVERIFY(setAutostartEnabled(entries.first(), true, user.path()));
    entries = scanAutostart({user.path()}, QStringLiteral("HeDE"));
    QVERIFY(entries.first().enabled);
    QCOMPARE(entries.first().entry.exec, QStringLiteral("mine --flag"));
}

QTEST_GUILESS_MAIN(TestAutostart)
#include "test_autostart.moc"
