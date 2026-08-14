#pragma once
// A registered custom type so the C++ write side can marshal
// Sysctl.ApplySettings' `a(ss)` argument — an array of (key, value) structs.
//
// This is the write-side analogue of the read-side container registration the
// Software panel does (aa{sv} -> QList<QVariantMap>, a{sx} -> QMap<QString,qlonglong>):
// HeDE declares the struct's QDBusArgument streaming once, registers it with
// qDBusRegisterMetaType, and the generated proxy then takes it like any value. The
// XML points qdbusxml2cpp at this type via a QtTypeName.In0 annotation.
#include <QDBusArgument>
#include <QList>
#include <QMetaType>
#include <QString>

struct SysctlSetting {
    QString key;
    QString value;
};
Q_DECLARE_METATYPE(SysctlSetting)

using SysctlSettings = QList<SysctlSetting>;

inline QDBusArgument &operator<<(QDBusArgument &arg, const SysctlSetting &s)
{
    arg.beginStructure();
    arg << s.key << s.value;
    arg.endStructure();
    return arg;
}

inline const QDBusArgument &operator>>(const QDBusArgument &arg, SysctlSetting &s)
{
    arg.beginStructure();
    arg >> s.key >> s.value;
    arg.endStructure();
    return arg;
}
