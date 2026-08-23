# Design: Project doctrine — controlled transvaluation

*Status: standing philosophy · Scope: the "why" beneath every design call across GeST / GeSI / HeDE and the ship-themed apps · Relates to: [hede-familiarity.md](hede-familiarity.md) (the tactical UX layer this governs), [desktop-environment.md](desktop-environment.md), [gangway-phase5-scope.md](gangway-phase5-scope.md)*

> **We are carrying people from a world they know to one worth arriving at. Familiarity is the rope over the canyon — never the destination — and we are only allowed to break what we can build back better.**

This is the spine the other design docs hang from. [hede-familiarity.md](hede-familiarity.md) says *where the controls go*; this says *why*, and gives us the language to catch ourselves when a design is drifting wrong.

The word we use for the whole program is **transvaluation** — borrowed, deliberately, from Nietzsche's *Genealogy of Morals* (and Michael Sugrue's lecture on it). Nietzsche's *Umwertung aller Werte* is the historical inversion of one value-system by another. Ours is smaller and gentler by design — **controlled** transvaluation — and the four ideas below are what "controlled" actually means in practice.

---

## 1. Familiarity is the scaffold, not the goal

You don't kill the old god before the new structure stands. A Windows user's muscle memory is the bridge we carry them across on — to Gentoo's depth, real package management, seamless Windows interop ([Gangway](gangway-phase5-scope.md)), a desktop that's genuinely *theirs*.

The test of any surface is **not** "does it feel like Windows." It is: **does the familiarity earn the right to lead someone somewhere Windows can't go?** The day muscle memory becomes the end rather than the means, we've built Windows worse and the old god has quietly won.

## 2. The hammer defines "controlled"

Nietzsche called his method "philosophising with a hammer." Sugrue's warning about it is the whole reason our transvaluation is *controlled*:

> "It very easily shades over to intellectual vandalism. It may be that everything that can be broken, ought not to be broken."

Breaking a convention is easy and *feels* like progress. The discipline is asking not whether a convention **can** be broken but whether it **ought** to be. Before moving anything a user's hands already know, run two tests:

1. **Genealogy** — *why does this convention exist, and whom did it serve?* (See §4.) A convention isn't sacred, but it isn't arbitrary either. Decide by history, not by taste or contrarian reflex.
2. **The creation debt** — *what better structure am I putting in its place?* No creation, no break.

## 3. Build from strength, never from ressentiment

This is the failure mode that has sunk a hundred Linux desktops, and it's a failure of *motive*, not mechanics.

Nietzsche distinguishes **master morality** — spontaneous self-affirmation, where the strong call their own vitality "good" — from **slave morality**, which is *reactive*: it first declares the powerful "evil," then derives its own "good" as the mere negation. Its engine is **ressentiment**: an impotent resentment that, unable to act, "becomes creative and gives birth to values."

**A project built out of ressentiment defines itself as anti-Windows / anti-Microsoft** — its virtues are just the inverse of Redmond's choices. That is slave morality in software, and it produces exactly the pathologies in §1 and §5.

Build instead from strength: the nautical **Helm** identity, Gentoo's real power, [Gangway](gangway-phase5-scope.md), the Hiedi assistant — because these are ours and alive, not because they spite anyone.

> **The tell of ressentiment: a feature whose only argument is "Windows doesn't let you."** When you catch that argument, stop. Re-derive the feature from an affirmative value, or drop it.

## 4. Origins are made, not eternal (genealogy as method)

Nietzsche's actual method is the *natural history of morality*: our categories aren't handed down from on high — they have a contingent, excavatable origin and a social function.

Every desktop convention is likewise **made**: Start bottom-left, close top-right, single- vs. double-click — historical accidents with functions, not laws of nature. This cuts both ways and is the engine of §2's first test:

- Because a convention is *made*, we are permitted to transvalue it.
- Because it *served a purpose*, we excavate that purpose before we touch it.

Decide what to keep and what to change by genealogy, not by reflex in either direction.

## 5. After you break, you must legislate

Nietzsche's "death of God" is the collapse of the scaffolding that held a morality up — leaving the morality with nothing underneath. The result is **nihilism** unless someone creates new values (the Übermensch as self-legislator).

The design corollary is §2's creation debt stated at full strength: **dissolving a habit obligates you to legislate a better structure in its place.** Breaking-for-its-own-sake — change with nothing affirmative behind it — is the vandalism mode, and it reads to the user as chaos.

The move done right is to **dissolve the border rather than demand a departure.** [Gangway](gangway-phase5-scope.md) — seamless per-window Windows apps on HeDE — is the exemplar: don't ask people to *leave* Windows; make the boundary vanish so the old god becomes one app among many on a stronger foundation. A new temple built with the old stones visible in its walls.

## The two symmetric failure modes (a summary)

| Failure | What it looks like | Which principle it violates |
|---|---|---|
| **Nihilistic change** | "Everything you know is wrong" — muscle memory gone, printer broken, user retreats. The tech was fine; the *transition* was violent. | §1 (no scaffold), §5 (broke without building) |
| **Taxidermy** | "Windows with a penguin" — the corpse propped in the chair. Nothing was actually transvalued. | §1 (familiarity became the goal) |
| **Ressentiment** | Virtues that are only the negation of Microsoft's. | §3 (built from spite, not strength) |

Neither pure preservation nor pure destruction is transvaluation. The narrow path between them is the doctrine.

## A note on the source, and the guardrail

We use Nietzsche as a **lens, not a mandate.** Sugrue himself does not endorse him — he calls the critique the most significant moral development since the Enlightenment while insisting the demolition may leave us worse off than what it smashed. Carry that ambivalence: **admire the artist, withhold assent from the vandal.** Transvaluation is a powerful way to see what we're doing; it is never a license to break things for the thrill of the hammer.
