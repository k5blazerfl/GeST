# Design: Consistent biome background through the boot chain

The boot should not be a badge. Instead of swapping the firmware's OEM logo for a
HeDE logo — one vanity plate for another — carry the **active biome's background**
unbroken from the moment GRUB draws through to the desktop. The boot becomes a fade
*into the world you're entering*, not an advertisement. The background is the quiet
identity; there is no logo to show, and nothing to shout.

## Principle

One image, four stages, no seams:

```
  GRUB menu  →  Plymouth splash  →  greetd login  →  desktop wallpaper
   (8-bit PNG)   (initramfs)         (greeter bg)     (helm bg)
        └──────────── the active biome's background ────────────┘
```

- **Consistent by default**: every stage shows the same biome background, so there
  is no black flash or logo swap at any handoff. Switching worlds re-skins the
  whole chain, not just the desktop.
- **The desktop is the only place divergence is allowed**: it tracks the biome
  background *by default*, but yields to a user-set custom wallpaper. When the user
  has overridden the wallpaper, the boot chain (GRUB / Plymouth / greeter) still
  shows the biome background and the desktop shows their choice — a deliberate,
  accepted break at the last step, never inside the boot.

## Single source of truth + the coordinator

The active biome (`world/id` in hede.conf) owns one **canonical background scene**.
Four consumers derive their asset from it:

| Stage | Asset today | Needs |
| --- | --- | --- |
| GRUB | `data/grub/hede/background.png` | 8-bit **per-channel**, non-interlaced, sized to the gfxmode |
| Plymouth | per-world `boot.png` (baked into initramfs) | same scene; regen on world switch |
| greetd | — (**missing link**) | greeter draws the same scene behind the login |
| Desktop | helm wallpaper | the biome wallpaper, unless user-overridden |

**`helm-theme` is the coordinator.** It already regenerates the desktop look on a
world switch; extend it to repaint all four from the biome scene — the "always-on
watcher" that was still outstanding in the biome-splash work. On a world change it:
1. writes the GRUB-formatted background + reruns the theme stage (or `grub-mkconfig`),
2. updates the Plymouth theme's `background.png` **and** triggers a quiet
   `genkernel --plymouth initramfs` rebuild (the early-boot stage can't repaint
   live — see Constraints),
3. points the greeter at the same scene,
4. sets the desktop wallpaper **iff** the user hasn't overridden it.

A single `wallpaper_overridden` flag (set when the user picks a custom wallpaper)
is what gates step 4 — the one seam where the desktop may diverge.

## Constraints (design around, don't fight)

- **GRUB decodes only 8-bit-per-channel, non-interlaced PNG.** A 16-bit image
  renders as rainbow tearing (lived that — fixed in the hede-0.7.2 build). The
  biome scene needs a GRUB-formatted variant, dithered if it has smooth gradients.
- **Plymouth's background is baked into the initramfs** — it cannot repaint live.
  A world switch that should re-skin the splash must rebuild the initramfs
  (`genkernel --plymouth initramfs`). That's the one place "consistent" costs a
  regen; accept it, and make it quiet/backgrounded.
- **Resolution**: GRUB scales the background to the gfxmode; a 1024×768 asset on a
  1440p/4K panel comes up soft. The canonical scene should be authored at (or above)
  the target's native resolution and downscaled per stage.

## Asset fidelity — the real polish lever

Encoding is not the bottleneck; the **source asset is**. The current Harbor
background is only ~6,300 unique colors at 1024×768 — it bands regardless of bit
depth, because the *scene* is low-fidelity, not because 8-bit-per-channel is
limiting (that's 16.7M colors, the standard display depth). Two things follow:

- **Author the biome scenes at high fidelity** — smooth true-colour gradients,
  native (or higher) resolution — so they look polished when carried through the
  chain. This is the highest-leverage fix and a per-world art task.
- **Dither only the GRUB stage as insurance** — if a high-fidelity scene still
  bands after downscale to the gfxmode, a subtle error-diffusion/blue-noise dither
  on that one variant smooths it. Keep it subtle: heavy dither bloats the PNG
  (noise doesn't compress) and grain shows on a boot screen. Dither is a finish,
  not a substitute for a good source.

## Phasing (slices)

1. **Greeter background** — the missing link: greetd draws the biome scene behind
   the login. Closes the one hard black-flash gap in the chain.
2. **Coordinator** — `helm-theme` repaints all four stages from the biome on a
   world switch, gated by `wallpaper_overridden` for the desktop; includes the
   backgrounded initramfs regen for the Plymouth stage.
3. **GRUB per-world variant** — generate the 8-bit, gfxmode-sized (dithered if
   needed) GRUB background per world.
4. **Quiet boot** — no logo/badge anywhere in the chain; drop any HeDE plate from
   the Plymouth theme so the scene stands alone. (Optional: a whisper-thin world
   name, off by default.)
5. **Asset refresh** — re-author the biome scenes at high fidelity + native res so
   the whole chain looks polished (the real quality work).

## Non-goals (v1)

- **A logo/badge** anywhere in the boot. The whole point is the scene, not a plate.
- **Live per-frame animation** in GRUB/Plymouth — a still biome scene, not a video.
- **Propagating a user's custom desktop wallpaper up the boot chain** — the boot
  chain always tracks the biome; the desktop is the only place a custom wallpaper
  applies. (GRUB/initramfs can't cheaply track an arbitrary runtime image anyway.)
