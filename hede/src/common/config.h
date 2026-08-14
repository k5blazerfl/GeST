#pragma once

#include <QString>

namespace helm {

// Reads HeDE's INI config ($XDG_CONFIG_HOME/hede/hede.conf by default).
// Phase 0 exposes exactly two keys, both defaulted. GeST will own this surface
// later; the pattern is established here.
class Config {
  public:
    Config();                             // default path
    explicit Config(const QString &path); // explicit path (tests)

    int panelHeight() const;         // [panel] height   (default 32)
    QString terminalCommand() const; // [terminal] command (default "foot")

    // Generic accessor for feature-specific keys (e.g. "wallpaper/mode").
    QString string(const QString &key, const QString &def = QString()) const;

  private:
    QString m_path;
};

} // namespace helm
