// GeST Control Center — Hostname panel, as a HeDE C++/Qt view would build it.
//
// The full path-B loop from C++, over TWO buses:
//   * READ / validate / render  — gestd on the SESSION bus (unprivileged),
//     via the qdbusxml2cpp proxy in hostname_interface.h.
//   * WRITE (Apply)             — the polkit-gated ROOT backend on the SYSTEM bus.
// No Portage, no Python in-process — just generated proxies.
//
// The GUI drives Hostname. The WRITE side is broadened past SetHostname with
// headless demonstrations across three more backend interfaces, each pairing with a
// gestd read the client already does:
//   --apply <name>              System.SetHostname(name, "/")
//   --apply-timezone <zone>     System.SetTimezone(zone, "/")        (localization)
//   --enable-service <name> <0|1>  Services.SetEnabled(name, on)
//   --control-service <name> <act> Services.Control(name, act)       (start/stop/…)
//   --apply-sysctl <key> <value>   Sysctl.ApplySettings([(key,value)], "/")
// The last exercises the write-side container type a(ss) (see sysctl_types.h).
// Run headless, these reach the real backend and polkit denies the un-prompted
// caller — which is exactly the proof that the system-bus/polkit path is wired.

#include <QApplication>
#include <QDBusConnection>
#include <QDBusMetaType>
#include <QDBusPendingReply>
#include <QFormLayout>
#include <QGroupBox>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QTextStream>
#include <QVBoxLayout>
#include <QVariantMap>
#include <QWidget>

#include "hostname_interface.h"         // gestd, session bus (reads)
#include "system_interface.h"           // root backend, system bus (writes)
#include "services_write_interface.h"   // root backend, system bus (writes)
#include "sysctl_write_interface.h"     // root backend, system bus (writes)
#include "sysctl_types.h"               // SysctlSettings: the a(ss) write type

static const QString kCoreService = QStringLiteral("org.gentoo.gest.Core");
static const QString kCorePath = QStringLiteral("/org/gentoo/gest/core/Hostname");
static const QString kBackendService = QStringLiteral("org.gentoo.gest");
static const QString kBackendPath = QStringLiteral("/org/gentoo/gest/System");
static const QString kServicesPath = QStringLiteral("/org/gentoo/gest/Services");
static const QString kSysctlPath = QStringLiteral("/org/gentoo/gest/Sysctl");

// The value following a "--flag" on the command line (or a fallback).
static QString argAfter(const QStringList &args, const QString &flag, const QString &fallback)
{
    const int i = args.indexOf(flag);
    return (i >= 0 && i + 1 < args.size()) ? args.at(i + 1) : fallback;
}

int main(int argc, char **argv)
{
    QApplication app(argc, argv);
    qDBusRegisterMetaType<SysctlSetting>();     // the a(ss) write element type
    qDBusRegisterMetaType<SysctlSettings>();
    const QStringList args = app.arguments();
    const bool once = args.contains(QStringLiteral("--once"));
    QTextStream out(stdout), err(stderr);

    // Read side: gestd on the session bus.
    OrgGentooGestCore1HostnameInterface hostname(kCoreService, kCorePath,
                                                 QDBusConnection::sessionBus());
    // Write side: the polkit root backend on the system bus — one proxy per
    // interface (all share the bus name org.gentoo.gest).
    OrgGentooGestSystemInterface backend(kBackendService, kBackendPath,
                                         QDBusConnection::systemBus());
    OrgGentooGestServicesInterface services(kBackendService, kServicesPath,
                                            QDBusConnection::systemBus());
    OrgGentooGestSysctlInterface sysctl(kBackendService, kSysctlPath,
                                        QDBusConnection::systemBus());

    // Every backend write returns (ok:b, output:s); print it (or the D-Bus error)
    // uniformly and map to an exit code.
    auto report = [&out](const QString &label, QDBusPendingReply<bool, QString> w) -> int {
        w.waitForFinished();
        if (w.isError()) {
            out << label << " -> D-Bus error: " << w.error().message() << "\n";
            return 1;
        }
        out << label << " -> ok=" << w.argumentAt<0>()
            << " output=" << w.argumentAt<1>() << "\n";
        return 0;
    };

    // Headless write demonstrations of the system-bus/polkit path (each needs
    // gest-backend installed and a polkit agent to actually succeed; un-prompted
    // they are denied, which still proves the call reached the backend).
    if (args.contains(QStringLiteral("--apply"))) {
        const QString name = argAfter(args, QStringLiteral("--apply"), QStringLiteral("gentoo"));
        return report(QStringLiteral("SetHostname('%1')").arg(name),
                      backend.SetHostname(name, QStringLiteral("/")));
    }
    if (args.contains(QStringLiteral("--apply-timezone"))) {
        const QString zone =
            argAfter(args, QStringLiteral("--apply-timezone"), QStringLiteral("UTC"));
        return report(QStringLiteral("SetTimezone('%1')").arg(zone),
                      backend.SetTimezone(zone, QStringLiteral("/")));
    }
    if (args.contains(QStringLiteral("--enable-service"))) {
        const int i = args.indexOf(QStringLiteral("--enable-service"));
        const QString name = (i + 1 < args.size()) ? args.at(i + 1) : QStringLiteral("sshd");
        const bool on = (i + 2 < args.size()) ? (args.at(i + 2) != QStringLiteral("0")) : true;
        return report(QStringLiteral("SetEnabled('%1', %2)").arg(name).arg(on),
                      services.SetEnabled(name, on));
    }
    if (args.contains(QStringLiteral("--control-service"))) {
        const int i = args.indexOf(QStringLiteral("--control-service"));
        const QString name = (i + 1 < args.size()) ? args.at(i + 1) : QStringLiteral("sshd");
        const QString action =
            (i + 2 < args.size()) ? args.at(i + 2) : QStringLiteral("restart");
        return report(QStringLiteral("Control('%1', '%2')").arg(name, action),
                      services.Control(name, action));
    }
    if (args.contains(QStringLiteral("--apply-sysctl"))) {
        const int i = args.indexOf(QStringLiteral("--apply-sysctl"));
        const QString key =
            (i + 1 < args.size()) ? args.at(i + 1) : QStringLiteral("vm.swappiness");
        const QString value = (i + 2 < args.size()) ? args.at(i + 2) : QStringLiteral("10");
        const SysctlSettings settings{SysctlSetting{key, value}};
        return report(QStringLiteral("ApplySettings([(%1, %2)])").arg(key, value),
                      sysctl.ApplySettings(settings, QStringLiteral("/")));
    }

    if (!hostname.isValid()) {
        err << "gestd unreachable on the session bus — start it with `gest-core`.\n";
        return 1;
    }
    QDBusPendingReply<QVariantMap> stateReply = hostname.GetState();
    stateReply.waitForFinished();
    if (stateReply.isError()) {
        err << "GetState failed: " << stateReply.error().message() << "\n";
        return 1;
    }
    QString current = stateReply.value().value(QStringLiteral("hostname")).toString();

    // --- the view -----------------------------------------------------------
    QWidget win;
    win.setWindowTitle(QStringLiteral("GeST — Hostname (HeDE reference)"));
    auto *box = new QGroupBox(QStringLiteral("Hostname"));
    auto *form = new QFormLayout(box);
    auto *currentLabel = new QLabel(current);
    auto *edit = new QLineEdit(current);
    auto *status = new QLabel;
    auto *preview = new QLabel;
    auto *check = new QPushButton(QStringLiteral("Validate + preview"));
    auto *apply = new QPushButton(QStringLiteral("Apply (writes via polkit)"));
    form->addRow(QStringLiteral("Current:"), currentLabel);
    form->addRow(QStringLiteral("New:"), edit);
    form->addRow(QString(), check);
    form->addRow(QString(), apply);
    form->addRow(QStringLiteral("Status:"), status);
    form->addRow(QStringLiteral("Preview:"), preview);
    auto *layout = new QVBoxLayout(&win);
    layout->addWidget(box);

    // Read side: validate a candidate + preview the config a write would produce.
    auto validateAndPreview = [&]() {
        const QString name = edit->text();
        QDBusPendingReply<bool, QString> v = hostname.Validate(name);
        v.waitForFinished();
        const bool ok = !v.isError() && v.argumentAt<0>();
        const QString message = v.isError() ? v.error().message() : v.argumentAt<1>();
        status->setText(ok ? QStringLiteral("✓ valid")
                           : QStringLiteral("✗ ") + message);
        QString rendered;
        if (ok) {
            QDBusPendingReply<QString> r = hostname.Render(name);
            r.waitForFinished();
            rendered = r.isError() ? QString() : r.value();
        }
        preview->setText(rendered.trimmed());
    };

    // Write side: apply the change through the polkit root backend, then re-read
    // the current value from gestd.
    auto applyChange = [&]() {
        const QString name = edit->text();
        QDBusPendingReply<bool, QString> w = backend.SetHostname(name, QStringLiteral("/"));
        w.waitForFinished();
        if (w.isError()) {
            status->setText(QStringLiteral("✗ write failed: ") + w.error().message());
            return;
        }
        status->setText((w.argumentAt<0>() ? QStringLiteral("✓ ") : QStringLiteral("✗ "))
                        + w.argumentAt<1>());
        QDBusPendingReply<QVariantMap> s = hostname.GetState();
        s.waitForFinished();
        if (!s.isError()) {
            current = s.value().value(QStringLiteral("hostname")).toString();
            currentLabel->setText(current);
        }
    };
    QObject::connect(check, &QPushButton::clicked, validateAndPreview);
    QObject::connect(apply, &QPushButton::clicked, applyChange);
    validateAndPreview();

    out << "GetState -> hostname=" << current
        << "  |  Validate('" << edit->text() << "') -> " << status->text()
        << "  |  Render -> " << preview->text() << "\n";

    if (once)
        return 0;
    win.show();
    return app.exec();
}
