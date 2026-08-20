#include "job.h"

#include <QPointer>
#include <QThread>

namespace helm::hold {

Job::Job(const QString &title, QObject *parent) : QObject(parent), _title(title) {
    [[maybe_unused]] static const int reg = qRegisterMetaType<helm::hold::Result>();
}

void Job::run(std::function<Result(const Progress &)> work) {
    if (_started)
        return;
    _started = true;

    // The worker captures only the shared cancel flag and a QPointer to us, so it
    // stays safe if the Job is destroyed mid-run: the cancel read is on the shared
    // flag, and the queued progress/finished emits are dropped when the guard is
    // null.
    QPointer<Job> self(this);
    auto cancel = _cancel;

    auto *thread = QThread::create([self, cancel, work = std::move(work)]() mutable {
        Progress p;
        p.cancelled = [cancel] { return cancel->load(); };
        p.step = [self](qint64 done, qint64 total, const QString &name) {
            if (!self)
                return;
            QMetaObject::invokeMethod(
                self, [self, done, total, name] { if (self) emit self->progress(done, total, name); },
                Qt::QueuedConnection);
        };
        const Result res = work(p);
        if (self)
            QMetaObject::invokeMethod(
                self, [self, res] { if (self) emit self->finished(res); }, Qt::QueuedConnection);
    });
    connect(thread, &QThread::finished, thread, &QThread::deleteLater);
    thread->start();
}

} // namespace helm::hold
