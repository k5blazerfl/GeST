#pragma once

#include <QString>
#include <QStringList>

namespace helm {

// Reads HeDE's INI config ($XDG_CONFIG_HOME/hede/hede.conf by default).
// GeST (and Barnacle, the panel editor) will write this surface; the pattern is
// established here.
class Config {
  public:
    Config();                             // default path
    explicit Config(const QString &path); // explicit path (tests)

    int panelHeight() const;         // [panel] height   (default 46)
    QString terminalCommand() const; // [terminal] command (default "foot")

    // [panel] applets — the ordered list of applets the bar builds, left→right.
    // Comma-separated in the INI; trimmed and lower-cased. When the key is
    // absent (or empty) this returns the built-in default lineup, so an
    // un-configured panel looks exactly as it always has. Unknown names are
    // preserved here and skipped (with a warning) by the panel's dispatch.
    QStringList panelApplets() const;

    // Generic accessor for feature-specific keys (e.g. "wallpaper/mode").
    QString string(const QString &key, const QString &def = QString()) const;

    // The backing INI path — for watching the file for live config changes.
    QString path() const { return m_path; }

  private:
    QString m_path;
};

} // namespace helm
