#include <QtTest>

#include "mpris.h"

class TestMedia : public QObject {
    Q_OBJECT
private slots:
    void serviceMatch() {
        QVERIFY(helm::isMprisService(QStringLiteral("org.mpris.MediaPlayer2.vlc")));
        QVERIFY(helm::isMprisService(QStringLiteral("org.mpris.MediaPlayer2.Pyrrha")));
        QVERIFY(!helm::isMprisService(QStringLiteral("org.freedesktop.Notifications")));
    }
    void trackFormat() {
        QCOMPARE(helm::formatTrack(QString(), QStringLiteral("A")), QString()); // no title → empty
        QCOMPARE(helm::formatTrack(QStringLiteral("Song"), QString()), QStringLiteral("Song"));
        QCOMPARE(helm::formatTrack(QStringLiteral("Song"), QStringLiteral("Band")),
                 QStringLiteral("Band — Song"));
    }
    void playPauseIcon() {
        QCOMPARE(helm::playPauseIconName(QStringLiteral("Playing")),
                 QStringLiteral("media-playback-pause"));
        QCOMPARE(helm::playPauseIconName(QStringLiteral("Paused")),
                 QStringLiteral("media-playback-start"));
        QCOMPARE(helm::playPauseIconName(QStringLiteral("Stopped")),
                 QStringLiteral("media-playback-start"));
    }
};

QTEST_MAIN(TestMedia)
#include "test_media.moc"
