#pragma once

#include <QString>
#include <QStringList>

namespace helm {

// Session power actions offered by the launcher's right rail.
enum class PowerAction { Suspend, Reboot, PowerOff, Lock, LogOut };

// A resolved power command: either a systemd-logind Manager method (Suspend/
// Reboot/PowerOff) or a shell argv (Lock via swaylock, LogOut via loginctl).
// Pure + unit-tested; invokePower() performs the side effect.
struct PowerCommand {
    enum Kind { Logind, Shell } kind;
    QString method;   // logind Manager method when kind == Logind
    QStringList argv; // program + args when kind == Shell
};

PowerCommand powerCommand(PowerAction a);

// Perform the action: call org.freedesktop.login1 over the system bus, or launch
// the shell argv. LogOut appends $XDG_SESSION_ID to the loginctl argv (no-op if
// the session can't be resolved, rather than terminating the wrong one).
void invokePower(PowerAction a);

} // namespace helm
