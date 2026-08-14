#pragma once

#include <QString>
#include <QStringList>
#include <QToolButton>

namespace helm {

class CoreClient;

// --- pure logic (unit-tested) ---
QString updatePillText(int count);                      // "" / "1 update" / "N updates"
bool updatePillVisible(int count);                      // count > 0
QStringList settingsEmbedArgs(const QString &moduleId); // {"--embed", id}

// Panel indicator: "N updates" when GeST reports pending @world updates, hidden
// otherwise. Reads via a shared CoreClient (the seam); no privilege.
class UpdatePill : public QToolButton {
    Q_OBJECT
  public:
    explicit UpdatePill(CoreClient *client, QWidget *parent = nullptr);

  private:
    void apply();
    CoreClient *m_client;
};

} // namespace helm
