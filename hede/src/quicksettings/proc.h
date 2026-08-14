#pragma once

#include <QString>
#include <QStringList>

namespace helm {

// Is a program on $PATH? (applets hide when their tool is missing)
bool haveProgram(const QString &program);

// Run a short command and capture stdout (trimmed). Blocks up to timeoutMs;
// returns "" on failure. Intended for fast CLIs (wpctl, brightnessctl).
QString runCapture(const QString &program, const QStringList &args, int timeoutMs = 500);

} // namespace helm
