#include "theme.h"

#include "world.h"

#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QSettings>
#include <QStandardPaths>
#include <QtMath>

namespace helm {

// The default latitude for follow-the-sun when [appearance] latitude is unset —
// a northern mid-latitude, a sane fallback with no location service.
static constexpr double kDefaultLatitude = 40.0;

bool isNightAt(const QDateTime &when, double latitudeDeg) {
    // Sunrise/sunset via a coarse solar-position model: solar declination from the
    // day-of-year, the sunrise hour-angle from declination × latitude, then the
    // half-day length that straddles local solar noon. Good enough to flip the
    // desktop light↔dark with the sun; not an almanac.
    const int doy = when.date().dayOfYear();
    const double lat = qDegreesToRadians(latitudeDeg);
    const double decl = qDegreesToRadians(23.44) * std::sin(2.0 * M_PI * (doy - 81) / 365.0);
    const double cosH = -std::tan(lat) * std::tan(decl);
    if (cosH <= -1.0)
        return false; // midnight sun — the sun never sets today
    if (cosH >= 1.0)
        return true; // polar night — the sun never rises today
    const double halfDay = std::acos(cosH) * 12.0 / M_PI; // hours from noon to sunset
    const QTime t = when.time();
    const double h = t.hour() + t.minute() / 60.0 + t.second() / 3600.0;
    return h < (12.0 - halfDay) || h >= (12.0 + halfDay);
}

bool isNightNow(double latitudeDeg) { return isNightAt(QDateTime::currentDateTime(), latitudeDeg); }

bool resolveDark(const QString &mode, bool legacyDark, double latitudeDeg) {
    const QString m = mode.trimmed().toLower();
    if (m == QLatin1String("dark"))
        return true;
    if (m == QLatin1String("light"))
        return false;
    if (m == QLatin1String("auto"))
        return isNightNow(latitudeDeg);
    return legacyDark; // unset / unrecognised → the pre-`mode` boolean
}

QString effectiveGtkTheme(const ThemeSpec &s) {
    if (!s.gtkTheme.isEmpty())
        return s.gtkTheme;
    return s.dark ? QStringLiteral("Adwaita-dark") : QStringLiteral("Adwaita");
}

QString gtkSettingsIni(const ThemeSpec &s) {
    QString out = QStringLiteral("[Settings]\n");
    out += QStringLiteral("gtk-application-prefer-dark-theme=%1\n").arg(s.dark ? 1 : 0);
    out += QStringLiteral("gtk-theme-name=%1\n").arg(effectiveGtkTheme(s));
    if (!s.iconTheme.isEmpty())
        out += QStringLiteral("gtk-icon-theme-name=%1\n").arg(s.iconTheme);
    return out;
}

namespace {

// Parse "#rrggbb" into 0..255 channels; false if not a 6-digit hex colour.
bool parseHex6(const QString &hex, int &r, int &g, int &b) {
    QString h = hex.trimmed();
    if (h.startsWith(QLatin1Char('#')))
        h = h.mid(1);
    if (h.size() != 6)
        return false;
    bool ok = false;
    const int v = h.toInt(&ok, 16);
    if (!ok)
        return false;
    r = (v >> 16) & 0xff;
    g = (v >> 8) & 0xff;
    b = v & 0xff;
    return true;
}

QString hex6(int r, int g, int b) {
    auto clamp = [](int c) { return c < 0 ? 0 : (c > 255 ? 255 : c); };
    return QString::asprintf("#%02x%02x%02x", clamp(r), clamp(g), clamp(b));
}

// Same luminance rule as helm::contrastText (appearance/palette.cpp): black on
// light bars, white on dark ones. Kept here so helm-theme-lib stays Core-only
// (no QColor/Qt6::Gui); test_theme asserts parity with the canonical colours.
QString contrastHex(const QString &bg) {
    int r = 0, g = 0, b = 0;
    if (!parseHex6(bg, r, g, b))
        return QStringLiteral("#ffffff");
    const double lum = 0.299 * r + 0.587 * g + 0.114 * b;
    return lum > 140 ? QStringLiteral("#000000") : QStringLiteral("#ffffff");
}

// Scale each channel by `f` (darken < 1) for subtle borders derived from a bar.
QString scaleHex(const QString &c, double f) {
    int r = 0, g = 0, b = 0;
    if (!parseHex6(c, r, g, b))
        return c;
    auto s = [f](int v) { return int(v * f + 0.5); };
    return hex6(s(r), s(g), s(b));
}

// Mix each channel toward white by `t` (0..1) for a brighter "accent_2" hi.
QString lightenHex(const QString &c, double t) {
    int r = 0, g = 0, b = 0;
    if (!parseHex6(c, r, g, b))
        return c;
    auto l = [t](int v) { return int(v + (255 - v) * t + 0.5); };
    return hex6(l(r), l(g), l(b));
}

// A "0.rrr, 0.ggg, 0.bbb" triple (Plymouth's Image.Text takes 0..1 floats).
QString rgbFloat(const QString &c) {
    int r = 0, g = 0, b = 0;
    if (!parseHex6(c, r, g, b))
        parseHex6(QStringLiteral("#3aa6c4"), r, g, b);
    return QString::asprintf("%.3f, %.3f, %.3f", r / 255.0, g / 255.0, b / 255.0);
}

} // namespace

QString defaultAccent() { return QStringLiteral("#3aa6c4"); }

QString themercBody(const ThemeSpec &s) {
    const QString accent = s.accent.isEmpty() ? QStringLiteral("#3aa6c4") : s.accent;
    const QString surface = s.dark ? QStringLiteral("#0e2c34") : QStringLiteral("#f6fafb");
    const QString activeText = contrastHex(accent);
    const QString surfaceText = contrastHex(surface);
    const QString mutedText = surfaceText + QStringLiteral("99"); // #rrggbbaa, dimmed

    QString o = QStringLiteral("# Helm titlebar skin - generated by helm-theme.\n"
                               "# Do not edit; regenerated on every theme change.\n");
    // The focused titlebar is a top-lit vertical gradient: the accent at the top
    // falling to a shadowed accent at the bottom. This is the frost/bevel of the
    // decoration_art contract rendered within labwc's real capability — labwc
    // titlebar backgrounds are Solid/Gradient only (no image/nine-slice), so a
    // gradient is the achievable painterly frame. `.color` stays the accent so
    // the bar still reads as the world colour.
    o += QStringLiteral("window.active.title.bg: Gradient Vertical\n");
    o += QStringLiteral("window.active.title.bg.color: %1\n").arg(accent);
    o += QStringLiteral("window.active.title.bg.colorTo: %1\n").arg(scaleHex(accent, 0.82));
    o += QStringLiteral("window.active.label.text.color: %1\n").arg(activeText);
    o += QStringLiteral("window.active.border.color: %1\n").arg(scaleHex(accent, 0.80));
    o += QStringLiteral("window.active.button.unpressed.image.color: %1\n").arg(activeText);
    o += QStringLiteral("window.inactive.title.bg.color: %1\n").arg(surface);
    o += QStringLiteral("window.inactive.label.text.color: %1\n").arg(mutedText);
    o += QStringLiteral("window.inactive.border.color: %1\n").arg(scaleHex(surface, 0.90));
    o += QStringLiteral("window.inactive.button.unpressed.image.color: %1\n").arg(mutedText);
    o += QStringLiteral("window.titlebar.padding.width: 8\n");
    o += QStringLiteral("window.titlebar.padding.height: 6\n");
    o += QStringLiteral("window.button.width: 22\n");
    o += QStringLiteral("window.button.height: 22\n");
    o += QStringLiteral("window.button.spacing: 6\n");
    o += QStringLiteral("window.button.hover.bg.color: %1\n").arg(surfaceText + QStringLiteral("1a"));
    o += QStringLiteral("window.button.hover.bg.corner-radius: 6\n");
    o += QStringLiteral("menu.items.bg.color: %1\n").arg(surface);
    o += QStringLiteral("menu.items.text.color: %1\n").arg(surfaceText);
    o += QStringLiteral("menu.items.active.bg.color: %1\n").arg(accent);
    o += QStringLiteral("menu.items.active.text.color: %1\n").arg(activeText);
    o += QStringLiteral("osd.bg.color: %1\n").arg(surface);
    o += QStringLiteral("osd.border.color: %1\n").arg(accent);
    o += QStringLiteral("osd.label.text.color: %1\n").arg(surfaceText);
    return o;
}

QString plymouthScriptBody(const QString &accent) {
    const QString a = accent.isEmpty() ? defaultAccent() : accent;
    // A deep shade of the accent for the pre-image fallback fill / letterbox,
    // shared with the GRUB desktop-color so the two boot stages read as one.
    const QString fill = rgbFloat(scaleHex(a, 0.16));
    const QString bar = rgbFloat(a);

    QString o = QStringLiteral(
        "// HeDE boot splash - generated by helm-theme.\n"
        "// Do not edit; regenerated on every theme/world change. The scene sits\n"
        "// under a thin progress tracker; the fallback fill and the bar track the\n"
        "// active world's accent. One 256-colour image keeps it light in the initramfs.\n"
        "\n"
        "screen_w = Window.GetWidth();\n"
        "screen_h = Window.GetHeight();\n"
        "\n"
        "// Fallback fill if the image can't load: a deep shade of the accent.\n");
    o += QStringLiteral("Window.SetBackgroundTopColor(%1);\n").arg(fill);
    o += QStringLiteral("Window.SetBackgroundBottomColor(%1);\n").arg(fill);
    o += QStringLiteral(
        "\n"
        "// Full-screen scene, scaled to fill the display.\n"
        "bg.sprite = Sprite(Image(\"background.png\").Scale(screen_w, screen_h));\n"
        "bg.sprite.SetPosition(0, 0, 0);\n"
        "\n"
        "// Progress tracker - bottom middle: an accent fill growing over a faint rail.\n"
        "track.w = screen_w * 0.30;\n"
        "track.x = screen_w / 2 - track.w / 2;\n"
        "track.y = screen_h - 54;\n"
        "\n"
        "rail.sprite = Sprite(Image.Text(\" \", 0.85, 0.9, 0.95).Scale(track.w, 3));\n"
        "rail.sprite.SetPosition(track.x, track.y, 1);\n"
        "rail.sprite.SetOpacity(0.18);\n"
        "\n");
    o += QStringLiteral("bar.pixel = Image.Text(\" \", %1);   // %2 accent\n").arg(bar, a);
    o += QStringLiteral(
        "bar.sprite = Sprite(bar.pixel.Scale(2, 3));\n"
        "bar.sprite.SetPosition(track.x, track.y, 2);\n"
        "\n"
        "fun boot_progress_cb(duration, pct) {\n"
        "    width = track.w * pct;\n"
        "    if (width < 2) width = 2;\n"
        "    bar.sprite.SetImage(bar.pixel.Scale(width, 3));\n"
        "    bar.sprite.SetPosition(track.x, track.y, 2);\n"
        "}\n"
        "Plymouth.SetBootProgressFunction(boot_progress_cb);\n"
        "\n"
        "// Boot messages are suppressed by the quiet cmdline; keep any off the clean splash.\n"
        "fun message_cb(text) { }\n"
        "Plymouth.SetMessageFunction(message_cb);\n");
    return o;
}

QString grubThemeBody(const QString &accent) {
    const QString a = accent.isEmpty() ? defaultAccent() : accent;
    const QString deep = scaleHex(a, 0.16);   // letterbox, shared with Plymouth
    const QString hi = lightenHex(a, 0.40);   // brightened accent_2 for the selection

    QString o = QStringLiteral(
        "# HeDE / GeST Installer - the Harbor GRUB theme, generated by helm-theme.\n"
        "# Do not edit; regenerated on every theme/world change. Pairs with the\n"
        "# Plymouth splash so the boot reads as one experience. The title + mark are\n"
        "# baked into background.png; this lays the boot menu + countdown over it, the\n"
        "# letterbox + highlighted entry tinted to the active world's accent. Consumed\n"
        "# by the live CD (ISO grub.cfg inject) and installed systems (GRUB_THEME).\n"
        "\n"
        "title-text: \"\"\n"
        "desktop-image: \"background.png\"\n");
    o += QStringLiteral("desktop-color: \"%1\"\n").arg(deep);
    o += QStringLiteral(
        "terminal-font: \"HeDE Sans Regular 18\"\n"
        "\n"
        "# The boot menu, lower-centre over the clear part of the background.\n"
        "+ boot_menu {\n"
        "    left       = 25%\n"
        "    top        = 47%\n"
        "    width      = 50%\n"
        "    height     = 34%\n"
        "    item_font          = \"HeDE Sans Regular 18\"\n"
        "    item_color         = \"#c6d9de\"\n");
    o += QStringLiteral("    selected_item_color = \"%1\"   # brightened accent - the highlighted entry\n").arg(hi);
    o += QStringLiteral(
        "    item_height        = 36\n"
        "    item_padding       = 6\n"
        "    item_spacing       = 4\n"
        "    item_icon_space    = 0\n"
        "}\n"
        "\n"
        "# Countdown (\"Booting in N seconds\"), just below the menu.\n"
        "+ label {\n"
        "    id    = \"__timeout__\"\n"
        "    top   = 84%\n"
        "    left  = 0\n"
        "    width = 100%\n"
        "    align = \"center\"\n"
        "    color = \"#8fb0b8\"\n"
        "    font  = \"HeDE Sans Regular 18\"\n"
        "    text  = \"Booting in %d seconds\"\n"
        "}\n"
        "\n"
        "# A one-line hint under the countdown.\n"
        "+ label {\n"
        "    top   = 89%\n"
        "    left  = 0\n"
        "    width = 100%\n"
        "    align = \"center\"\n"
        "    color = \"#5f7a82\"\n"
        "    font  = \"HeDE Sans Regular 18\"\n"
        "    text  = \"Up/Down to choose  ·  Enter to boot  ·  E to edit  ·  C for a console\"\n"
        "}\n");
    return o;
}

ThemeSpec parseThemeArgs(const QStringList &args) {
    ThemeSpec s;
    for (const QString &a : args) {
        if (a == QLatin1String("--dark")) {
            s.dark = true;
            s.mode = QStringLiteral("dark");
        } else if (a == QLatin1String("--light")) {
            s.dark = false;
            s.mode = QStringLiteral("light");
        } else if (a.startsWith(QLatin1String("--mode=")))
            s.mode = a.section(QLatin1Char('='), 1).trimmed().toLower(); // dark|light|auto
        else if (a.startsWith(QLatin1String("--accent=")))
            s.accent = a.section(QLatin1Char('='), 1);
        else if (a.startsWith(QLatin1String("--gtk-theme=")))
            s.gtkTheme = a.section(QLatin1Char('='), 1);
        else if (a.startsWith(QLatin1String("--icon-theme=")))
            s.iconTheme = a.section(QLatin1Char('='), 1);
    }
    return s;
}

static bool writeText(const QString &path, const QString &text) {
    QDir().mkpath(QFileInfo(path).absolutePath());
    QFile f(path);
    if (!f.open(QIODevice::WriteOnly | QIODevice::Text))
        return false;
    return f.write(text.toUtf8()) >= 0;
}

QStringList applyTheme(const ThemeSpec &sIn, bool persistAppearance) {
    const QString base = QStandardPaths::writableLocation(QStandardPaths::GenericConfigLocation);

    // Resolve the `mode` knob (dark/light/auto) into the concrete light/dark the
    // GTK + labwc themes are generated against. `auto` uses the stored latitude
    // (default mid-latitude); the running shell re-resolves it on the clock.
    ThemeSpec s = sIn;
    if (!s.mode.isEmpty()) {
        const double lat = QSettings(base + QStringLiteral("/hede/hede.conf"), QSettings::IniFormat)
                               .value(QStringLiteral("appearance/latitude"), kDefaultLatitude)
                               .toDouble();
        s.dark = resolveDark(s.mode, s.dark, lat);
    }

    const QString gtk = gtkSettingsIni(s);
    QStringList written;

    for (const QString &ver : {QStringLiteral("gtk-3.0"), QStringLiteral("gtk-4.0")}) {
        const QString path = base + QLatin1Char('/') + ver + QStringLiteral("/settings.ini");
        if (writeText(path, gtk))
            written << path;
    }

    // HeDE's own palette (read by the shell via Config). Skipped when the accent
    // is world-derived, so a world switch isn't frozen as an explicit choice.
    if (persistAppearance) {
        const QString hede = base + QStringLiteral("/hede/hede.conf");
        QDir().mkpath(QFileInfo(hede).absolutePath());
        QSettings conf(hede, QSettings::IniFormat);
        // `mode` is the source of truth; `dark` is kept in sync (as the resolved
        // snapshot) for any pre-`mode` reader. A plain --accent call leaves the
        // stored mode untouched.
        if (!s.mode.isEmpty())
            conf.setValue(QStringLiteral("appearance/mode"), s.mode);
        conf.setValue(QStringLiteral("appearance/dark"), s.dark);
        if (!s.accent.isEmpty())
            conf.setValue(QStringLiteral("appearance/accent"), s.accent);
        conf.sync();
        if (conf.status() == QSettings::NoError)
            written << hede;
    }

    // The Helm labwc titlebar skin, under $XDG_DATA_HOME so it shadows the
    // system default in /usr/share/themes. labwc re-reads it on --reconfigure.
    const QString dataBase = QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation);
    const QString themerc = dataBase + QStringLiteral("/themes/Helm/labwc/themerc");
    if (writeText(themerc, themercBody(s)))
        written << themerc;

    // Stage the boot splash (Plymouth + GRUB) so it tracks the same accent. This
    // only writes user-space staging files; a privileged step installs them and
    // rebuilds the initramfs (see stageBootTheme).
    written << stageBootTheme(s.accent);

    return written;
}

QStringList writeBootTheme(const QString &dir, const QString &accent) {
    QStringList written;

    const QString script = dir + QStringLiteral("/plymouth/hede/hede.script");
    if (writeText(script, plymouthScriptBody(accent)))
        written << script;

    const QString grub = dir + QStringLiteral("/grub/hede/theme.txt");
    if (writeText(grub, grubThemeBody(accent)))
        written << grub;

    return written;
}

QStringList stageBootTheme(const QString &accent) {
    const QString base = QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation);
    const QString dir = base + QStringLiteral("/hede/boot");
    QStringList written = writeBootTheme(dir, accent);
    const QString scene = emitBootScene(dir, activeWorldId());
    if (!scene.isEmpty())
        written << scene;
    return written;
}

QString activeWorldId() {
    const QString base = QStandardPaths::writableLocation(QStandardPaths::GenericConfigLocation);
    QSettings conf(base + QStringLiteral("/hede/hede.conf"), QSettings::IniFormat);
    return conf.value(QStringLiteral("world/id"), QStringLiteral("harbor")).toString();
}

QString activeAccent() {
    const QString base = QStandardPaths::writableLocation(QStandardPaths::GenericConfigLocation);
    QSettings conf(base + QStringLiteral("/hede/hede.conf"), QSettings::IniFormat);
    const QString explicitAccent = conf.value(QStringLiteral("appearance/accent")).toString();
    if (!explicitAccent.isEmpty())
        return explicitAccent;
    const QString a = loadWorld(activeWorldId()).accent;
    return a.isEmpty() ? defaultAccent() : a;
}

QString emitBootScene(const QString &dir, const QString &worldId) {
    const QString src = loadWorld(worldId).bootPath();
    if (src.isEmpty())
        return QString(); // no per-world scene → leave the installed default
    const QString dst = dir + QStringLiteral("/plymouth/hede/background.png");
    QDir().mkpath(QFileInfo(dst).absolutePath());
    QFile::remove(dst); // QFile::copy refuses to overwrite an existing target
    return QFile::copy(src, dst) ? dst : QString();
}

bool setWorld(const QString &id) {
    if (!loadWorld(id).valid())
        return false; // no such installed world — leave everything as-is

    const QString base = QStandardPaths::writableLocation(QStandardPaths::GenericConfigLocation);
    const QString hede = base + QStringLiteral("/hede/hede.conf");
    QDir().mkpath(QFileInfo(hede).absolutePath());
    {
        QSettings conf(hede, QSettings::IniFormat);
        conf.setValue(QStringLiteral("world/id"), id);
        conf.remove(QStringLiteral("appearance/accent")); // adopt the world's accent
        conf.sync();
        if (conf.status() != QSettings::NoError)
            return false;
    }
    // Regenerate the window chrome from the now-active world (labwc + GTK).
    applyThemeFromWorld();
    return true;
}

QStringList applyThemeFromWorld() {
    const QString base = QStandardPaths::writableLocation(QStandardPaths::GenericConfigLocation);
    QSettings conf(base + QStringLiteral("/hede/hede.conf"), QSettings::IniFormat);

    ThemeSpec s;
    // The `mode` knob (dark/light/auto) drives the labwc/GTK themes; fall back to
    // the legacy `dark` bool when it's unset. `auto` resolves on the clock here.
    s.mode = conf.value(QStringLiteral("appearance/mode")).toString();
    const bool legacyDark = conf.value(QStringLiteral("appearance/dark")).toBool();
    const double lat =
        conf.value(QStringLiteral("appearance/latitude"), kDefaultLatitude).toDouble();
    s.dark = resolveDark(s.mode, legacyDark, lat);
    s.gtkTheme = conf.value(QStringLiteral("appearance/gtk-theme")).toString();
    s.iconTheme = conf.value(QStringLiteral("appearance/icon-theme")).toString();
    // Accent precedence mirrors helm::effectiveAccent (see activeAccent).
    s.accent = activeAccent();
    return applyTheme(s, /*persistAppearance=*/false);
}

} // namespace helm
