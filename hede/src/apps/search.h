#pragma once

#include <QString>
#include <QStringList>
#include <QVector>

#include "desktopentry.h"

namespace helm {

// Fuzzy subsequence score of `query` against `text` (case-insensitive): the
// query chars must appear in order. Higher is better (bonuses for a prefix
// match, word-boundary hits, and consecutive runs); -1 if not a subsequence.
int fuzzyScore(const QString &text, const QString &query);

// Apps whose name/id fuzzy-matches `query`, best first. Empty query returns the
// entries unchanged (already name-sorted).
QVector<DesktopEntry> rankEntries(const QVector<DesktopEntry> &entries, const QString &query);

// Executable command names found on $PATH (deduped, sorted).
QStringList pathExecutables();

// The $PATH executables that fuzzy-match `query`, best first, capped at `limit`.
// Empty query returns nothing (we don't list every binary unprompted).
QStringList matchingExecutables(const QStringList &all, const QString &query, int limit = 8);

} // namespace helm
