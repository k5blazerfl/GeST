#pragma once

/* Reuse xpet's sprite skins (folders of .xpm frames per state). */
#ifndef PET_ASSET_DIR   /* overridden by the build to the installed skin path */
#define PET_ASSET_DIR   "/home/charron/hiedi-lab/xpet/pets/neko"
#endif

/* control channel the Hiedi brain drives the pet through (say / mood) —
 * same protocol + path as xpet, so the existing bridge works unchanged.
 * "" = auto: $XDG_RUNTIME_DIR/hiedi-pet.ctl */
#define PET_CTRL_FIFO   ""

#define FRAME_DURATION_MS 200   /* ms between animation frames */
#define PET_TOP_MARGIN    48    /* px below the top edge where the pet perches */
#define PET_SPEED         14    /* px per frame while wandering */
#define PET_AWAY_MS       60000 /* idle ms before the pet is free to roam (screensaver) */
#define WANDER_MARGIN     80    /* keep this far from screen edges while roaming */

#define SPEECH_BASE_MS     3500 /* base bubble time; + per line of text */
#define FONT_SCALE         2    /* 8x8 font → 16px text */
#define BUBBLE_MAX_W       700  /* bubble surface width (word-wrap boundary) */
#define BUBBLE_MAX_H       200  /* bubble surface height (fits up to ~8 wrapped lines) */

/* notification card (readable cairo/pango text, its own surface) */
#define NOTIF_MAX_W        440  /* card max width  */
#define NOTIF_MAX_H        200  /* card max height */
#define NOTIF_MARGIN       18   /* gap from the screen corner */
#define NOTIF_FONT         "Sans 11"
#define NOTIF_CORNER       0    /* 0=top-right 1=top-left 2=bottom-right 3=bottom-left */
#define EMOTE_MS           5200 /* she emotes this long under the card = message lifetime */
