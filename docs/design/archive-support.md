# Design: Archive support — Seahorse as a full archive manager

Implementation plan to grow HeDE's archive support from a broad **reader** + common
**creator** into a real, in-place **archive manager**, plus the power features
(encryption, more formats, safety) that make it trustworthy. All of it lands inside
Seahorse over the shared `hold-core` engine — Hold folded into the capital ship
(see [hold.md](hold.md)); there is no separate app.

One-line vision: **an archive is a folder you can also edit** — open it, walk it,
add to it, delete from it, lock it, all in the one window.

## Where we are (the baseline)

`hold-core` (`hede/src/hold/`, libarchive) today:

- **Reads** essentially everything libarchive can (`format_all` + `filter_all`):
  zip, tar, 7z, rar (read-only), cpio, iso, xar, cab, lha… with gzip/bzip2/xz/zstd/
  lz4/lzip/… filters.
- **Creates** a clean common set: zip/cbz, 7z, and tar + gzip/bzip2/xz.
- **Browses in place** (`ArchiveModel`) and **extracts** whole-or-selected from
  Seahorse.

What it is **not** yet: it can't **modify** an existing archive, has no
**encryption**, no **progress/cancel**, loads the table of contents
**synchronously**, and its safety is a single Zip-Slip guard. A strong reader and a
competent creator — not a manager.

## Locked decisions

Agreed in the design discussion (2026-08-20):

- **A · Mutation = streaming copy-rewrite.** libarchive can't edit in place, so
  every mutation reads the source entry-by-entry into a fresh archive — skipping
  deletes, renaming on the fly, appending adds — then atomically swaps it over the
  original. One pass, no full extraction to disk, format-preserving. Rejected:
  extract-all-→-modify-→-recreate (O(whole archive) per edit, loses format nuance)
  and zip-specific in-place append (not worth special-casing).
- **B · Encryption is backed by the Keychain.** Encrypted archives become a
  first-class customer of HeDE's own Secret Service vault (`gest/core/keychain`):
  prompt for a passphrase, offer "remember" → store in the vault, retrieve on
  re-open. Seahorse (C++) reaches it over the `org.freedesktop.secrets` D-Bus API
  the keychain daemon provides — no new secret store.
- **C · Progress/cancel is in-window; the desktop job/notification integration is
  DEFERRED and its own design process.** Long archive operations need a real
  progress channel (bytes/entries, cancel) — that plumbing is in scope. Surfacing
  those jobs through HeDE's notification/background-job system (`hede/src/notify`) —
  so a big extract keeps reporting after you navigate away — is **out of scope
  here**; HeDE's notification model isn't ready for background-job progress. This
  plan does progress **in-window** (a Seahorse progress panel) and leaves a clean
  seam for that future integration. **Circle back** once the job-notification
  design exists.
- **D · A real safety pass.** Beyond Zip-Slip: symlink-escape and absolute-path
  entries, decompression-ratio / entry-count caps (zip bombs), non-UTF-8 filename
  decoding (CP437 / Shift-JIS zips render as mojibake today), and overwrite-conflict
  resolution (today it silently clobbers/skips).
- **E · The cheap format wins.** zstd/lz4 **creation**, broaden `isArchive` so the
  formats libarchive already reads (cpio/iso/…) become browsable, a
  compression-level/format compress dialog, and archive **test/verify**.

## Architecture

### `hold-core` grows three capabilities

1. **`hold::Job` — a cancellable, progress-reporting operation.** The current
   fire-and-forget `extractAll`/`extract`/`create` become `Job`s that run on a
   worker thread and emit `progress(done, total, currentName)` and honour a
   `cancel()`. Seahorse's `runBusy`/throbber is the *idle* animator; a `Job` adds a
   determinate progress panel for the heavy ones. **The `Job` interface is the seam
   the future desktop job-notification design plugs into** — nothing else changes
   when that lands.

2. **`hold::rewrite(src, dst, Edits)` — the streaming mutation engine (decision A).**
   `Edits = { add: [{fsPath, innerPath}], remove: [inner…], rename: [{from, to}] }`.
   Detect the source's format + filter, open a matching writer, copy every source
   entry (applying removes/renames), append the adds, then `rename(2)` the temp over
   the original (atomic; never corrupts the source on failure/cancel). Delete /
   rename / add / new-folder-in-archive all reduce to one `rewrite`.

3. **Passphrases (decision B).** `archive_read_add_passphrase` on the reader and
   encrypted writers (`zip:encryption=aes256`, 7z) on the create/rewrite path,
   driven by a `PassphraseProvider` callback. Seahorse implements the provider
   against the Secret Service (prompt → vault lookup/store).

Plus the decision-D/E leaf work: extend `safeJoin` (symlinks/absolute), ratio/size
caps, `hdrcharset` filename decoding, an overwrite-policy enum, zstd/lz4 write
filters, a broadened `isArchive`, and a `test()` (read-through, no extraction).

### Seahorse touchpoints

- The **`_inArchive` read-only guard is lifted for mutation**: inside an archive,
  Delete / Rename / New Folder / paste-in now route to `hold::rewrite`;
  drag-out extracts, drag-in adds.
- A **compress dialog**: format, compression level, password (→ Keychain), and
  (where supported) split size — replacing the silent "Compress to .zip".
- A **passphrase dialog** wired to the vault, and a **progress panel** (determinate,
  cancellable) for `Job`s over a size threshold.

## Phasing

Ordered so the plumbing de-risks the rest and trust lands before power.

### A0 · Job plumbing & async load — ✅ shipped
`hold::Job` (worker thread, progress, cancel); the TOC read goes **async** so huge /
network archives don't freeze the browse; an in-window progress panel + cancel in
Seahorse. **Explicitly leaves the desktop job-notification integration to its own
design** (decision C) — `Job` is the seam.

### A1 · Safety pass (decision D) — ✅ shipped
Symlink/absolute-path guards, decompression-ratio + entry-count caps,
filename-encoding decode, overwrite-conflict resolution (replace / skip / keep-both).
Low-glamour, high-trust; belongs before we start *writing* into archives.
Delivered as: symlink-escape guard + skipped-entry reporting; zip-bomb `Limits`
(size / entry-count / ratio); UTF-8-else-CP437 filename decode; an `Overwrite`
policy in hold-core with a Seahorse pre-scan-and-prompt. All guard logic is pure
and unit-tested (`test-holdcore`).

### A2 · The streaming manager (decision A — the headline)
`hold::rewrite` + Seahorse in-archive mutation: **delete, rename, new folder, add
(drag-in / paste), drag-out to extract.** Archives become editable folders.

### A3 · Encryption + Keychain (decision B)
Read passphrase-prompted archives; create/rewrite **encrypted** (AES-256 zip, 7z);
Keychain-backed "remember this archive's passphrase" over the Secret Service.

### A4 · Power wins (decision E)
zstd/lz4 creation, broadened `isArchive`, the compression-level/format compress
dialog, archive test/verify, and split volumes where the format allows.

## Boundaries, non-goals & dependencies

- **Desktop-wide job/progress notifications — deferred, separate design (decision
  C).** Progress is in-window until HeDE's notification/background-job model is
  designed; the `hold::Job` seam is the hand-off point.
- **RAR stays read-only** — libarchive can't write rar; not a bug, a format reality.
- **No repair/recovery** of corrupt archives.
- **No nested-archive drill-in** (archive within a browsed archive) in v1 — carried
  over from [hold.md](hold.md)'s non-goals; revisit if demand appears.
- **Encrypted 7z / AES-zip write** depends on the linked libarchive's build options;
  A3 verifies the shipped libarchive exposes them (fallback: encrypted zip only).

## Risks & watch-items

- **Atomic swap correctness** — `rewrite` must never leave the user with a truncated
  archive: temp-then-rename, fsync, and cancel/​failure must restore the original
  untouched. This is the single highest-stakes piece.
- **Progress granularity** — libarchive reports per-entry, not smooth per-byte for
  every format; the panel must degrade gracefully to indeterminate (the throbber)
  when totals are unknown.
- **Keychain availability** — encrypted archives must still work with no vault /
  denied access (fall back to a one-shot prompt); never hard-block on the daemon.
- **Filename encoding** — heuristic decode can guess wrong; keep a raw-bytes escape
  hatch so nothing is unextractable.

## Relation to existing work

- Builds directly on the folded Hold ([hold.md](hold.md)) and the shared
  `hold-core` engine; SeFE ([sefe.md](sefe.md)) is the one and only surface.
- Encryption makes the **Keychain / Secret Service vault** (`gest/core/keychain`)
  its first real consumer beyond Gangway.
- The deferred progress-notification integration will couple to HeDE's notification
  daemon (`hede/src/notify`) — tracked here, designed elsewhere.
