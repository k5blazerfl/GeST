// GeST Control Center — Hostname panel, as a HeDE C++/Qt view would build it.
//
// It talks to gestd over the session bus through the qdbusxml2cpp-generated proxy
// (hostname_interface.h): GetState() reads the current hostname (a{sv} ->
// QVariantMap), Validate() checks a candidate ((b,s) -> bool + message), Render()
// previews the /etc/conf.d/hostname a write would produce. Reads/validation/render
// all stay in Python core behind gestd; applying is a write on the polkit backend.

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

#include "hostname_interface.h"

static const QString kService = QStringLiteral("org.gentoo.gest.Core");
static const QString kPath = QStringLiteral("/org/gentoo/gest/core/Hostname");

int main(int argc, char **argv)
{
    QApplication app(argc, argv);
    const bool once = app.arguments().contains(QStringLiteral("--once"));
    QTextStream out(stdout), err(stderr);

    // The generated proxy — used exactly like a local object.
    OrgGentooGestCore1HostnameInterface hostname(kService, kPath,
                                                 QDBusConnection::sessionBus());
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
    const QString current = stateReply.value().value(QStringLiteral("hostname")).toString();

    // --- the view -----------------------------------------------------------
    QWidget win;
    win.setWindowTitle(QStringLiteral("GeST — Hostname (HeDE reference)"));
    auto *box = new QGroupBox(QStringLiteral("Hostname"));
    auto *form = new QFormLayout(box);
    auto *edit = new QLineEdit(current);
    auto *status = new QLabel;
    auto *preview = new QLabel;
    auto *check = new QPushButton(QStringLiteral("Validate + preview"));
    form->addRow(QStringLiteral("Current:"), new QLabel(current));
    form->addRow(QStringLiteral("New:"), edit);
    form->addRow(QString(), check);
    form->addRow(QStringLiteral("Status:"), status);
    form->addRow(QStringLiteral("Preview:"), preview);
    auto *layout = new QVBoxLayout(&win);
    layout->addWidget(box);

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
    QObject::connect(check, &QPushButton::clicked, validateAndPreview);
    validateAndPreview();

    out << "GetState -> hostname=" << current
        << "  |  Validate('" << edit->text() << "') -> " << status->text()
        << "  |  Render -> " << preview->text() << "\n";

    if (once)
        return 0;   // headless proof: fetched, validated, rendered — done.
    win.show();
    return app.exec();
}
