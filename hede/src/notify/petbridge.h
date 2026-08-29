#pragma once

namespace helm {

struct Notification;

// Forward a shown notification to Hiedi's desktop pet (helm-pet) over its control
// FIFO, so she presents it as a card + run-in choreography. A no-op if the pet
// isn't running (no FIFO, or no reader) — the pet is entirely optional, and
// helm-notifyd never blocks or fails because of it.
void petNotify(const Notification &n);

} // namespace helm
