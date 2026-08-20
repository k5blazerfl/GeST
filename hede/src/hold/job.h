#pragma once

#include "holdcore.h"

#include <QObject>

#include <atomic>
#include <functional>
#include <memory>

// hold::Job — a cancellable, progress-reporting archive operation (A0,
// docs/design/archive-support.md). The heavy hold-core ops run inside a Job on a
// worker thread; it emits progress()/finished() (queued to the thread that created
// it) and honours a cooperative cancel(). This is the seam a future desktop
// job/notification design plugs into — nothing else changes when that lands.
//
// Lifetime: keep the Job alive until finished() fires (the usual pattern is to
// connect finished() → deleteLater()). The cancel flag is shared with the worker,
// so cancel() is safe even as the Job is being torn down.
namespace helm::hold {

class Job : public QObject {
    Q_OBJECT
public:
    explicit Job(const QString &title, QObject *parent = nullptr);

    QString title() const { return _title; }

    // Run `work` on a worker thread, handing it a Progress that marshals step()
    // onto progress() and reads the cancel flag. Emits finished() when done (with
    // Result{ok=false, error="cancelled"} if cancelled). Call once per Job.
    void run(std::function<Result(const Progress &)> work);

public slots:
    void cancel() { _cancel->store(true); }

signals:
    void progress(qint64 done, qint64 total, const QString &name);
    void finished(const helm::hold::Result &result);

private:
    QString _title;
    std::shared_ptr<std::atomic_bool> _cancel = std::make_shared<std::atomic_bool>(false);
    bool _started = false;
};

} // namespace helm::hold
