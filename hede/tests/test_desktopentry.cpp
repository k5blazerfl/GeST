#include <QtTest>

#include <QDir>
#include <QTemporaryDir>

#include "desktopentry.h"

class TestDesktopEntry : public QObject {
    Q_OBJECT
private slots:
    void parseFields() {
        const QString text = QStringLiteral("[Desktop Entry]\n"
                                            "Type=Application\n"
                                            "Name=Text Editor\n"
                                            "Name[fr]=Éditeur\n"
                                            "Comment=Edit text files\n"
                                            "Exec=editor %U\n"
                                            "Icon=accessories-text-editor\n");
        const helm::DesktopEntry e = helm::parseDesktopEntry(text, QStringLiteral("editor"));
        QCOMPARE(e.name, QStringLiteral("Text Editor")); // locale key ignored
        QCOMPARE(e.comment, QStringLiteral("Edit text files"));
        QCOMPARE(e.icon, QStringLiteral("accessories-text-editor"));
        QCOMPARE(e.type, QStringLiteral("Application"));
        QCOMPARE(e.id, QStringLiteral("editor"));
    }

    void parsesMimeTypesAndFiltersHandlers() {
        const QString viewer = QStringLiteral(
            "[Desktop Entry]\nType=Application\nName=Image Viewer\nExec=view %U\n"
            "MimeType=image/png;image/jpeg;\n");
        const QString editor = QStringLiteral(
            "[Desktop Entry]\nType=Application\nName=Editor\nExec=edit %U\n"
            "MimeType=text/plain;\n");
        const helm::DesktopEntry v = helm::parseDesktopEntry(viewer, QStringLiteral("view"));
        QCOMPARE(v.mimeTypes, (QStringList{"image/png", "image/jpeg"})); // ; split, no empties

        const QVector<helm::DesktopEntry> all{
            v, helm::parseDesktopEntry(editor, QStringLiteral("edit"))};
        const auto png = helm::handlersForMimeType(all, QStringLiteral("image/png"));
        QCOMPARE(png.size(), 1);
        QCOMPARE(png.first().name, QStringLiteral("Image Viewer"));
        QVERIFY(helm::handlersForMimeType(all, QStringLiteral("application/pdf")).isEmpty());
        QVERIFY(helm::handlersForMimeType(all, QString()).isEmpty()); // empty mime → none
    }

    void parsesJumpListActions() {
        const QString text = QStringLiteral("[Desktop Entry]\n"
                                            "Type=Application\n"
                                            "Name=Browser\n"
                                            "Exec=browser %U\n"
                                            "Actions=new-window;private;\n"
                                            "\n"
                                            "[Desktop Action new-window]\n"
                                            "Name=New Window\n"
                                            "Exec=browser --new-window\n"
                                            "\n"
                                            "[Desktop Action private]\n"
                                            "Name=New Private Window\n"
                                            "Exec=browser --private %u\n");
        const helm::DesktopEntry e = helm::parseDesktopEntry(text, QStringLiteral("browser"));
        QCOMPARE(e.name, QStringLiteral("Browser"));
        QCOMPARE(e.actions.size(), 2);
        QCOMPARE(e.actions[0].id, QStringLiteral("new-window"));
        QCOMPARE(e.actions[0].name, QStringLiteral("New Window"));
        QCOMPARE(e.actions[1].name, QStringLiteral("New Private Window"));
        // field codes stripped in an action's exec too
        QCOMPARE(helm::commandArgv(e.actions[1].exec),
                 (QStringList{QStringLiteral("browser"), QStringLiteral("--private")}));
    }

    void noActionsWhenAbsent() {
        const QString text = QStringLiteral("[Desktop Entry]\nType=Application\nName=X\nExec=x\n");
        QCOMPARE(helm::parseDesktopEntry(text, QStringLiteral("x")).actions.size(), 0);
    }

    void fieldCodesStripped() {
        helm::DesktopEntry e;
        e.exec = QStringLiteral("editor --flag %U %i");
        QCOMPARE(helm::commandArgv(e),
                 (QStringList{QStringLiteral("editor"), QStringLiteral("--flag")}));
    }

    void literalPercentKept() {
        helm::DesktopEntry e;
        e.exec = QStringLiteral("prog 100%%done");
        QCOMPARE(helm::commandArgv(e),
                 (QStringList{QStringLiteral("prog"), QStringLiteral("100%done")}));
    }

    void filterCaseInsensitive() {
        QVector<helm::DesktopEntry> all;
        helm::DesktopEntry a;
        a.name = QStringLiteral("Firefox");
        helm::DesktopEntry b;
        b.name = QStringLiteral("Files");
        all << a << b;
        const auto r = helm::filterEntries(all, QStringLiteral("fire"));
        QCOMPARE(r.size(), 1);
        QCOMPARE(r.first().name, QStringLiteral("Firefox"));
        QCOMPARE(helm::filterEntries(all, QString()).size(), 2); // empty → all
    }

    void scanExcludesAndDedupes() {
        QTemporaryDir hi; // higher priority
        QTemporaryDir lo; // lower priority
        write(hi, QStringLiteral("good.desktop"),
              QStringLiteral("[Desktop Entry]\nType=Application\nName=Good\nExec=good\n"));
        write(hi, QStringLiteral("nodisplay.desktop"),
              QStringLiteral("[Desktop Entry]\nType=Application\nName=Hidden\nExec=x\nNoDisplay=true\n"));
        write(hi, QStringLiteral("link.desktop"),
              QStringLiteral("[Desktop Entry]\nType=Link\nName=Site\nURL=http://x\n"));
        // same id in the lower-priority dir must NOT override the higher one
        write(lo, QStringLiteral("good.desktop"),
              QStringLiteral("[Desktop Entry]\nType=Application\nName=Override\nExec=bad\n"));

        const auto entries = helm::scanDesktopEntries({hi.path(), lo.path()});
        QCOMPARE(entries.size(), 1);
        QCOMPARE(entries.first().name, QStringLiteral("Good"));
        QCOMPARE(entries.first().exec, QStringLiteral("good"));
    }

private:
    static void write(const QTemporaryDir &dir, const QString &name, const QString &body) {
        QFile f(QDir(dir.path()).filePath(name));
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Text));
        f.write(body.toUtf8());
    }
};

QTEST_MAIN(TestDesktopEntry)
#include "test_desktopentry.moc"
