// GeST Control Center — Hostname panel, as a HeDE C++/Qt view would build it.
//
// The full path-B loop from C++, over TWO buses:
//   * READ / validate / render  — gestd on the SESSION bus (unprivileged),
//     via the qdbusxml2cpp proxy in hostname_interface.h.
//   * WRITE (Apply)             — the polkit-gated ROOT backend on the SYSTEM bus,
//     via system_interface.h. SetHostname triggers a polkit prompt.
// No Portage, no Python in-process — just two generated proxies.

#include <QApplication>
#include <QDBusConnection>
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

#include "hostname_interface.h"   // gestd, session bus (reads)
#include "system_interface.h"     // root backend, system bus (writes)

static const QString kCoreService = QStringLiteral("org.gentoo.gest.Core");
static const QString kCorePath = QStringLiteral("/org/gentoo/gest/core/Hostname");
static const QString kBackendService = QStringLiteral("org.gentoo.gest");
static const QString kBackendPath = QStringLiteral("/org/gentoo/gest/System");

int main(int argc, char **argv)
{
    QApplication app(argc, argv);
    const QStringList args = app.arguments();
    const bool once = args.contains(QStringLiteral("--once"));
    const bool applyOnly = args.contains(QStringLiteral("--apply"));
    QTextStream out(stdout), err(stderr);

    // Read side: gestd on the session bus.
    OrgGentooGestCore1HostnameInterface hostname(kCoreService, kCorePath,
                                                 QDBusConnection::sessionBus());
    // Write side: the polkit root backend on the system bus.
    OrgGentooGestSystemInterface backend(kBackendService, kBackendPath,
                                         QDBusConnection::systemBus());

    // --apply: attempt the write and report — a headless demonstration of the
    // system-bus/polkit path (needs gest-backend installed to actually succeed).
    if (applyOnly) {
        const int i = args.indexOf(QStringLiteral("--apply"));
        const QString name = (i + 1 < args.size()) ? args.at(i + 1) : QStringLiteral("gentoo");
        QDBusPendingReply<bool, QString> w = backend.SetHostname(name, QStringLiteral("/"));
        w.waitForFinished();
        if (w.isError())
            out << "SetHostname('" << name << "') -> D-Bus error: " << w.error().message() << "\n";
        else
            out << "SetHostname('" << name << "') -> ok=" << w.argumentAt<0>()
                << " output=" << w.argumentAt<1>() << "\n";
        return w.isError() ? 1 : 0;
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
