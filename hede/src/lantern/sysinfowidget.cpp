#include "sysinfowidget.h"

#include "widgets.h"

#include <QFile>
#include <QFrame>
#include <QLabel>
#include <QStorageInfo>
#include <QTimer>
#include <QVBoxLayout>

namespace helm {

static QString readProc(const QString &path) {
    QFile f(path);
    if (!f.open(QIODevice::ReadOnly | QIODevice::Text))
        return QString();
    return QString::fromUtf8(f.readAll());
}

LanternSysinfo::LanternSysinfo(QWidget *parent) : QWidget(parent) {
    setObjectName(QStringLiteral("LanternSysinfo"));

    auto *frame = new QFrame(this);
    frame->setObjectName(QStringLiteral("LanternWidgetCard"));
    frame->setFrameShape(QFrame::StyledPanel);
    auto *v = new QVBoxLayout(frame);
    v->setContentsMargins(10, 8, 10, 8);
    v->setSpacing(2);

    m_disk = new QLabel(frame);
    m_memory = new QLabel(frame);
    m_uptime = new QLabel(frame);
    m_uptime->setEnabled(false); // muted
    v->addWidget(m_disk);
    v->addWidget(m_memory);
    v->addWidget(m_uptime);

    auto *outer = new QVBoxLayout(this);
    outer->setContentsMargins(0, 0, 0, 0);
    outer->addWidget(frame);

    refresh();
    auto *timer = new QTimer(this);
    timer->setInterval(5000); // a slow refresh while the drawer is open
    connect(timer, &QTimer::timeout, this, &LanternSysinfo::refresh);
    timer->start();
}

void LanternSysinfo::refresh() {
    const QStorageInfo root = QStorageInfo::root();
    const qint64 total = root.bytesTotal();
    const qint64 used = total - root.bytesAvailable();
    m_disk->setText(tr("Disk  %1 / %2  (%3%)")
                        .arg(formatBytes(used), formatBytes(total))
                        .arg(usedPercent(used, total)));

    const MemInfo mem = parseMemInfo(readProc(QStringLiteral("/proc/meminfo")));
    const qint64 usedKb = mem.totalKb - mem.availableKb;
    m_memory->setText(tr("Memory  %1 / %2  (%3%)")
                          .arg(formatBytes(usedKb * 1024), formatBytes(mem.totalKb * 1024))
                          .arg(usedPercent(usedKb, mem.totalKb)));

    m_uptime->setText(formatUptime(parseUptimeSeconds(readProc(QStringLiteral("/proc/uptime")))));
}

} // namespace helm
