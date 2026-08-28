#pragma once

#include <QString>

namespace helm {

// Reads HeDE's INI config ($XDG_CONFIG_HOME/hede/hede.conf by default).
// GeST (and Barnacle, the panel editor) will write this surface; the pattern is
// established here. The ordered [panel] applets list lives in barnacle-lib
// (helm::PanelLayout) — the shared engine the bar and the editor both use.
class Config {
  public:
    Config();                             // default path
    explicit Config(const QString &path); // explicit path (tests)

    int panelHeight() const;         // [panel] height   (default 46)
    QString terminalCommand() const; // [terminal] command (default "textant")

    // Generic accessor for feature-specific keys (e.g. "wallpaper/mode").
    QString string(const QString &key, const QString &def = QString()) const;

    // The backing INI path — for watching the file for live config changes.
    QString path() const { return m_path; }

  private:
    QString m_path;
};

} // namespace helm
