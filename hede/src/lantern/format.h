#pragma once

#include "notification.h"

#include <QString>

class QDateTime;

// Pure display helpers for the Lantern notification list (unit-tested, no Qt
// Widgets / D-Bus). docs/design/lantern.md.
namespace helm {

// The primary line for a history entry: "App — Summary", or just the summary /
// app when the other is empty, or a placeholder when both are.
QString entryTitle(const Notification &n);

// A short human "time ago" for `received` relative to `now`: "just now",
// "5m ago", "3h ago", "2d ago", else the ISO date for anything a week old.
// Returns an empty string for an invalid timestamp.
QString relativeTime(const QDateTime &received, const QDateTime &now);

} // namespace helm
