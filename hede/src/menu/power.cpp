#include "power.h"

#include "launch.h"

#include <QDBusConnection>
#include <QDBusInterface>

namespace helm {

PowerCommand powerCommand(PowerAction a) {
    switch (a) {
    case PowerAction::Suspend:
        return {PowerCommand::Logind, QStringLiteral("Suspend"), {}};
    case PowerAction::Reboot:
        return {PowerCommand::Logind, QStringLiteral("Reboot"), {}};
    case PowerAction::PowerOff:
        return {PowerCommand::Logind, QStringLiteral("PowerOff"), {}};
    case PowerAction::Lock:
        return {PowerCommand::Shell, {}, {QStringLiteral("swaylock"), QStringLiteral("-f")}};
    case PowerAction::LogOut:
        return {PowerCommand::Shell, {}, {QStringLiteral("loginctl"), QStringLiteral("terminate-session")}};
    }
    return {PowerCommand::Logind, QString(), {}};
}

void invokePower(PowerAction a) {
    const PowerCommand c = powerCommand(a);
    if (c.kind == PowerCommand::Logind) {
        QDBusInterface mgr(QStringLiteral("org.freedesktop.login1"),
                           QStringLiteral("/org/freedesktop/login1"),
                           QStringLiteral("org.freedesktop.login1.Manager"),
                           QDBusConnection::systemBus());
        mgr.call(c.method, true); // interactive = true (polkit may prompt)
        return;
    }

    QStringList argv = c.argv;
    if (a == PowerAction::LogOut) {
        const QString sid = qEnvironmentVariable("XDG_SESSION_ID");
        if (sid.isEmpty())
            return; // don't guess a session to terminate
        argv << sid;
    }
    if (!argv.isEmpty())
        helm::launchDetached(argv.first(), argv.mid(1));
}

} // namespace helm
