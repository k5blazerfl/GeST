#pragma once

#include <QString>
#include <QToolButton>

namespace helm {

class CoreClient;

// --- pure indicator logic (unit-tested) ---
QString updatePillText(int count); // "" / "1 update" / "N updates"
bool updatePillVisible(int count); // count > 0

// A panel indicator: "N updates" when GeST reports pending @world updates,
// hidden otherwise. Reads via CoreClient (the seam); no privilege.
class UpdatePill : public QToolButton {
    Q_OBJECT
  public:
    explicit UpdatePill(QWidget *parent = nullptr);

  private:
    void apply(int count);
    CoreClient *m_client;
};

} // namespace helm
