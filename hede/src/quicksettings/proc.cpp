#include "proc.h"

#include <QProcess>
#include <QStandardPaths>

namespace helm {

bool haveProgram(const QString &program) {
    return !QStandardPaths::findExecutable(program).isEmpty();
}

QString runCapture(const QString &program, const QStringList &args, int timeoutMs) {
    QProcess p;
    p.start(program, args);
    if (!p.waitForFinished(timeoutMs))
        return QString();
    if (p.exitStatus() != QProcess::NormalExit || p.exitCode() != 0)
        return QString();
    return QString::fromUtf8(p.readAllStandardOutput()).trimmed();
}

} // namespace helm
