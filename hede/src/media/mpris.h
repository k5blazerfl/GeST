#pragma once

#include <QString>
#include <QWidget>

class QLabel;
class QToolButton;

namespace helm {

// --- pure logic (unit-tested) ---
bool isMprisService(const QString &busName);                      // org.mpris.MediaPlayer2.*
QString formatTrack(const QString &title, const QString &artist); // "Artist — Title"
QString playPauseIconName(const QString &playbackStatus);         // start / pause

// Panel media controls for the first available MPRIS2 player: previous /
// play-pause / next + the current track. Hidden when no player is present.
class MprisApplet : public QWidget {
    Q_OBJECT
  public:
    explicit MprisApplet(QWidget *parent = nullptr);

  private slots:
    void onNameOwnerChanged(const QString &name, const QString &oldOwner, const QString &newOwner);
    void onPropertiesChanged();

  private:
    void pickPlayer();
    void refresh();
    void call(const QString &method);

    QString m_player; // current player bus name, empty if none
    QToolButton *m_prev;
    QToolButton *m_playPause;
    QToolButton *m_next;
    QLabel *m_title;
};

} // namespace helm
