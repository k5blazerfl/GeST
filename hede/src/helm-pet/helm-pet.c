/*
 * helm-pet — HeDE's native desktop pet.
 *
 * A lean, Wayland-native (wlr-layer-shell) on-screen pet. It reuses xpet's .xpm
 * sprite skins and the same control FIFO, so the Hiedi brain bridge drives it
 * unchanged. Phase 1: render the animated sprite on an overlay layer surface,
 * perched at the top, with `mood` switching from the control channel. Movement,
 * window-awareness (foreign-toplevel), and idle-wander (idle-notify) come next.
 *
 * > Hiedi / HeDE 2026
 */
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/timerfd.h>
#include <unistd.h>

#include <math.h>
#include <time.h>

#include <cairo/cairo.h>
#include <pango/pangocairo.h>

#include <wayland-client.h>
#include "wlr-layer-shell-unstable-v1-client-protocol.h"
#include "wlr-foreign-toplevel-management-unstable-v1-client-protocol.h"
#include "ext-idle-notify-v1-client-protocol.h"

#include "config.h"
#include "font8x8_basic.h"

/* ------------------------------------------------------------------ skin model */
/* States we load from the skin (must match xpet's folder names). */
static const char *STATE_NAMES[] = {
	"idle", "sleeping", "happy", "dragged",
	"walk_east", "walk_west", "walk_north", "walk_south",
};
#define N_STATES ((int)(sizeof(STATE_NAMES) / sizeof(STATE_NAMES[0])))

struct anim {
	struct wl_buffer **frames;  /* one immutable shm buffer per frame */
	int n_frames;
};

static struct anim anims[N_STATES];
static int sprite_w = 0, sprite_h = 0;

/* ------------------------------------------------------------------ wayland state */
static struct wl_display    *display;
static struct wl_compositor *compositor;
static struct wl_shm        *shm;
static struct zwlr_layer_shell_v1 *layer_shell;

static struct wl_surface          *surface;
static struct zwlr_layer_surface_v1 *layer_surface;

static uint8_t *pool_data;      /* mmap of the shm pool holding every frame */
static struct wl_shm_pool *pool;
static struct wl_buffer *blank_pet;   /* transparent buffer to "hide" without unmapping */

static int   cur_state = 0;     /* index into anims[] */
static int   cur_frame = 0;
static int   configured = 0;
static int   running = 1;
static int   hidden = 0;        /* true → get out of the way (fullscreen/maximized) */

/* outputs + input (for positioning and idle detection) */
static struct wl_output *output;
static struct wl_seat   *seat;
static int out_w = 0, out_h = 0, out_scale = 1;

/* idle-awareness: roam only when the user is away */
static struct ext_idle_notifier_v1     *idle_notifier;
static struct ext_idle_notification_v1 *idle_notification;
static int away = 0;

/* movement (layer-shell margins as position) */
static double pos_x = 100, pos_y = PET_TOP_MARGIN;
static double tgt_x, tgt_y;
static int    have_target = 0;
static long   wander_wait_ms = 0;
static int    IDX_IDLE, IDX_WE, IDX_WW, IDX_WN, IDX_WS, IDX_HAPPY;

static int logical_w(void) { return out_w > 0 ? out_w / out_scale : 1920; }
static int logical_h(void) { return out_h > 0 ? out_h / out_scale : 1080; }
static int perch_x(void)  { return (logical_w() - sprite_w) / 2; }

/* control channel (brain → body) + event channel (body → brain) */
static int  ctrl_fd = -1;
static char ctrl_path[512];
static char evt_path[512];
static struct wl_pointer *pointer;
#define BTN_LEFT 0x110

/* speech bubble (a second layer surface with 8x8 bitmap text) */
static struct wl_surface           *bubble_surface;
static struct zwlr_layer_surface_v1 *bubble_ls;
static struct wl_buffer            *bubble_buffer;
static uint32_t                    *bubble_pixels;
static int  bubble_configured = 0;
static int  speaking = 0;
static long speech_ms = 0;
static long speech_ttl = 0;     /* current bubble's lifetime (scales with lines) */
static int  bub_w = 0, bub_h = 0;   /* the drawn bubble's size (≤ MAX); rest transparent */
#define BUBBLE_PAD  8
#define LINE_GAP    4
#define LINE_H      (8 * FONT_SCALE + LINE_GAP)

/* notification card (cairo/pango, readable font, its own corner surface) */
static struct wl_surface           *notif_surface;
static struct zwlr_layer_surface_v1 *notif_ls;
static struct wl_buffer            *notif_buffer;
static uint32_t                    *notif_pixels;
static int  notif_configured = 0;
static int  card_w = 0, card_h = 0;   /* rendered card size within the max surface */
static int  card_screen_x = 0, card_screen_y = 0;   /* card top-left on screen */

/* notification choreography: NONE → RUN_IN → EMOTE → RUN_BACK → NONE */
enum notif_phase { NF_NONE, NF_RUN_IN, NF_EMOTE, NF_RUN_BACK };
static enum notif_phase nphase = NF_NONE;
static long  emote_ms = 0;
static int   came_from_right = 1;   /* which edge she ran in from (for run-back) */

/* ------------------------------------------------------------------ xpm loader */
/* Resolve an XPM colour spec: None → transparent, #rrggbb → hex, or a named X
 * colour (xpm skins commonly use "black"/"white"). Unknown → opaque black so a
 * sprite never silently vanishes. */
static uint32_t xpm_color(const char *c)
{
	while (*c == ' ' || *c == '\t') { c++; }
	if (strncasecmp(c, "None", 4) == 0) { return 0x00000000u; }
	if (c[0] == '#') {
		unsigned r = 0, g = 0, b = 0;
		sscanf(c + 1, "%2x%2x%2x", &r, &g, &b);
		return 0xFF000000u | (r << 16) | (g << 8) | b;
	}
	static const struct { const char *n; uint32_t rgb; } named[] = {
		{"black", 0x000000}, {"white", 0xFFFFFF}, {"gray", 0x808080},
		{"grey", 0x808080}, {"red", 0xFF0000}, {"green", 0x008000},
		{"blue", 0x0000FF}, {"yellow", 0xFFFF00}, {"cyan", 0x00FFFF},
		{"magenta", 0xFF00FF}, {"orange", 0xFFA500}, {"brown", 0xA52A2A},
		{"pink", 0xFFC0CB}, {"purple", 0x800080}, {NULL, 0},
	};
	for (int i = 0; named[i].n; i++) {
		if (strcasecmp(c, named[i].n) == 0) { return 0xFF000000u | named[i].rgb; }
	}
	return 0xFF000000u;   /* unknown named colour → opaque black */
}

/* Parse a (cpp=1) XPM file into a freshly malloc'd ARGB8888 buffer. */
static uint32_t *xpm_load(const char *path, int *out_w, int *out_h)
{
	FILE *f = fopen(path, "r");
	if (!f) {
		return NULL;
	}
	fseek(f, 0, SEEK_END);
	long len = ftell(f);
	fseek(f, 0, SEEK_SET);
	char *src = malloc((size_t)len + 1);
	if (!src || fread(src, 1, (size_t)len, f) != (size_t)len) {
		free(src);
		fclose(f);
		return NULL;
	}
	src[len] = '\0';
	fclose(f);

	/* collect the quoted string tokens in order */
	char **tok = NULL;
	int ntok = 0, cap = 0;
	for (char *p = src; *p;) {
		if (*p != '"') { p++; continue; }
		char *start = ++p;
		while (*p && *p != '"') { p++; }
		if (!*p) { break; }
		*p = '\0';
		if (ntok == cap) { cap = cap ? cap * 2 : 64; tok = realloc(tok, sizeof(char *) * cap); }
		tok[ntok++] = start;
		p++;
	}

	uint32_t *px = NULL;
	int w = 0, h = 0, ncolors = 0, cpp = 0;
	if (ntok < 1 || sscanf(tok[0], "%d %d %d %d", &w, &h, &ncolors, &cpp) != 4 || cpp != 1) {
		goto done;
	}
	if (ntok < 1 + ncolors + h) {
		goto done;
	}

	/* char -> ARGB colour map */
	uint32_t map[256];
	int has[256];
	memset(has, 0, sizeof(has));
	for (int i = 0; i < ncolors; i++) {
		const char *t = tok[1 + i];
		unsigned char key = (unsigned char)t[0];
		const char *c = strstr(t, " c ");
		map[key] = c ? xpm_color(c + 3) : 0x00000000u;
		has[key] = 1;
	}

	px = malloc(sizeof(uint32_t) * (size_t)w * (size_t)h);
	for (int y = 0; y < h; y++) {
		const char *row = tok[1 + ncolors + y];
		for (int x = 0; x < w; x++) {
			unsigned char key = (unsigned char)row[x];
			px[y * w + x] = has[key] ? map[key] : 0x00000000;
		}
	}
	*out_w = w;
	*out_h = h;

done:
	free(tok);
	free(src);
	return px;
}

/* count frames 0.xpm,1.xpm,... in a state dir */
static int count_frames(const char *state)
{
	int n = 0;
	for (;;) {
		char path[600];
		snprintf(path, sizeof(path), "%s/%s/%d.xpm", PET_ASSET_DIR, state, n);
		if (access(path, R_OK) != 0) { break; }
		n++;
	}
	return n;
}

/* ------------------------------------------------------------------ shm + frames */
static int load_skin(void)
{
	/* pass 1: frame counts + sprite size (from the first idle frame) */
	int total = 0;
	for (int s = 0; s < N_STATES; s++) {
		anims[s].n_frames = count_frames(STATE_NAMES[s]);
		total += anims[s].n_frames;
	}
	if (total == 0) {
		fprintf(stderr, "helm-pet: no frames under %s\n", PET_ASSET_DIR);
		return -1;
	}
	{
		char path[600];
		snprintf(path, sizeof(path), "%s/idle/0.xpm", PET_ASSET_DIR);
		int w, h;
		uint32_t *probe = xpm_load(path, &w, &h);
		if (!probe) { fprintf(stderr, "helm-pet: can't read idle/0.xpm\n"); return -1; }
		sprite_w = w; sprite_h = h;
		free(probe);
	}

	size_t frame_bytes = (size_t)sprite_w * sprite_h * 4;
	size_t pool_size = frame_bytes * (size_t)total;

	int fd = memfd_create("helm-pet-pool", MFD_CLOEXEC);
	if (fd < 0 || ftruncate(fd, (off_t)pool_size) < 0) {
		perror("helm-pet: shm");
		return -1;
	}
	pool_data = mmap(NULL, pool_size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
	if (pool_data == MAP_FAILED) { perror("mmap"); return -1; }
	pool = wl_shm_create_pool(shm, fd, (int32_t)pool_size);

	/* pass 2: parse each frame into the pool and make an immutable wl_buffer */
	size_t off = 0;
	for (int s = 0; s < N_STATES; s++) {
		anims[s].frames = calloc((size_t)anims[s].n_frames, sizeof(struct wl_buffer *));
		for (int i = 0; i < anims[s].n_frames; i++) {
			char path[600];
			snprintf(path, sizeof(path), "%s/%s/%d.xpm", PET_ASSET_DIR, STATE_NAMES[s], i);
			int w, h;
			uint32_t *px = xpm_load(path, &w, &h);
			if (px && w == sprite_w && h == sprite_h) {
				memcpy(pool_data + off, px, frame_bytes);
			}
			free(px);
			anims[s].frames[i] = wl_shm_pool_create_buffer(
				pool, (int32_t)off, sprite_w, sprite_h, sprite_w * 4,
				WL_SHM_FORMAT_ARGB8888);
			off += frame_bytes;
		}
	}
	close(fd);
	return 0;
}

/* ------------------------------------------------------------------ speech bubble */
static struct wl_buffer *make_buffer(int w, int h, uint32_t **out)
{
	size_t size = (size_t)w * h * 4;
	int fd = memfd_create("helm-pet-bubble", MFD_CLOEXEC);
	if (fd < 0 || ftruncate(fd, (off_t)size) < 0) { return NULL; }
	uint32_t *data = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
	if (data == MAP_FAILED) { close(fd); return NULL; }
	struct wl_shm_pool *p = wl_shm_create_pool(shm, fd, (int32_t)size);
	struct wl_buffer *b = wl_shm_pool_create_buffer(p, 0, w, h, w * 4,
	                                                WL_SHM_FORMAT_ARGB8888);
	wl_shm_pool_destroy(p);
	close(fd);
	*out = data;
	return b;
}

static int clampi(int v, int lo, int hi) { return v < lo ? lo : (v > hi ? hi : v); }

static void px_set(uint32_t *px, int x, int y, uint32_t c)
{
	if (x >= 0 && x < BUBBLE_MAX_W && y >= 0 && y < BUBBLE_MAX_H) { px[y * BUBBLE_MAX_W + x] = c; }
}

/* blit one line of 8x8 text at (x0,y0) */
static void blit_line(int x0, int y0, const char *s, uint32_t ink)
{
	int glyph = 8 * FONT_SCALE;
	for (int i = 0; s[i]; i++) {
		unsigned char c = (unsigned char)s[i];
		if (c >= 128) { c = '?'; }
		const char *g = font8x8_basic[c];
		for (int row = 0; row < 8; row++) {
			unsigned char bits = (unsigned char)g[row];
			for (int col = 0; col < 8; col++) {
				if ((bits >> col) & 1) {
					for (int sy = 0; sy < FONT_SCALE; sy++) {
						for (int sx = 0; sx < FONT_SCALE; sx++) {
							px_set(bubble_pixels, x0 + i * glyph + col * FONT_SCALE + sx,
							       y0 + row * FONT_SCALE + sy, ink);
						}
					}
				}
			}
		}
	}
}

/* word-wrap text into a multi-line bubble, sizing bub_w/bub_h to the content */
static void draw_bubble(const char *text)
{
	if (!bubble_pixels) { return; }
	const uint32_t WHITE = 0xFFFFFFFFu, INK = 0xFF202020u, EDGE = 0xFF303030u;
	for (int i = 0; i < BUBBLE_MAX_W * BUBBLE_MAX_H; i++) { bubble_pixels[i] = 0; }

	int glyph = 8 * FONT_SCALE;
	int wrap = (BUBBLE_MAX_W - 2 * BUBBLE_PAD - 16) / glyph;   /* chars per line */
	if (wrap < 6) { wrap = 6; } else if (wrap > 120) { wrap = 120; }
	int max_lines = (BUBBLE_MAX_H - 2 * BUBBLE_PAD) / LINE_H;
	if (max_lines > 8) { max_lines = 8; } else if (max_lines < 1) { max_lines = 1; }

	char lines[8][128];
	int nlines = 0, cur = 0;
	lines[0][0] = '\0';
	const char *p = text;
	while (*p && nlines < max_lines) {
		while (*p == ' ' || *p == '\t') { p++; }
		if (!*p) { break; }
		const char *w = p;
		while (*p && *p != ' ' && *p != '\t') { p++; }
		int wl = (int)(p - w);
		if (wl > wrap) { wl = wrap; }                 /* hard-break a giant word */
		int need = (cur > 0 ? cur + 1 : 0) + wl;
		if (need > wrap && cur > 0) {
			lines[nlines][cur] = '\0';
			nlines++; cur = 0;
			if (nlines >= max_lines) { break; }
		}
		if (cur > 0 && cur < 127) { lines[nlines][cur++] = ' '; }
		for (int i = 0; i < wl && cur < 127; i++) { lines[nlines][cur++] = w[i]; }
	}
	if (nlines < max_lines) { lines[nlines][cur] = '\0'; nlines++; }
	if (*p) {                                          /* text overflowed → ellipsis */
		int L = (int)strlen(lines[nlines - 1]);
		if (L > wrap - 3) { L = wrap - 3; }
		if (L < 0) { L = 0; }
		snprintf(lines[nlines - 1] + L, sizeof(lines[nlines - 1]) - (size_t)L, "...");
	}

	int longest = 0;
	for (int i = 0; i < nlines; i++) {
		int l = (int)strlen(lines[i]);
		if (l > longest) { longest = l; }
	}
	bub_w = longest * glyph + 16;
	bub_h = nlines * LINE_H + 2 * BUBBLE_PAD - LINE_GAP;
	if (bub_w > BUBBLE_MAX_W) { bub_w = BUBBLE_MAX_W; }
	if (bub_h > BUBBLE_MAX_H) { bub_h = BUBBLE_MAX_H; }
	int bx = (BUBBLE_MAX_W - bub_w) / 2;
	if (bx < 0) { bx = 0; }

	for (int y = 0; y < bub_h; y++) {
		for (int x = bx; x < bx + bub_w; x++) { px_set(bubble_pixels, x, y, WHITE); }
	}
	for (int x = bx; x < bx + bub_w; x++) { px_set(bubble_pixels, x, 0, EDGE); px_set(bubble_pixels, x, bub_h - 1, EDGE); }
	for (int y = 0; y < bub_h; y++) { px_set(bubble_pixels, bx, y, EDGE); px_set(bubble_pixels, bx + bub_w - 1, y, EDGE); }

	for (int i = 0; i < nlines; i++) {
		blit_line(bx + 8, BUBBLE_PAD + i * LINE_H, lines[i], INK);
	}

	speech_ttl = SPEECH_BASE_MS + (long)nlines * 1400;
	if (speech_ttl > 14000) { speech_ttl = 14000; }
}

static void show_bubble(const char *text)
{
	if (!bubble_ls || !bubble_configured || !bubble_buffer) { return; }
	draw_bubble(text);
	int bx = clampi((int)pos_x + sprite_w / 2 - BUBBLE_MAX_W / 2, 0,
	                logical_w() > BUBBLE_MAX_W ? logical_w() - BUBBLE_MAX_W : 0);
	int by = (int)pos_y - bub_h - 10;                 /* above the pet if it fits */
	if (by < 0) { by = (int)pos_y + sprite_h + 10; }  /* else below */
	zwlr_layer_surface_v1_set_margin(bubble_ls, by, 0, 0, bx);
	wl_surface_attach(bubble_surface, bubble_buffer, 0, 0);
	wl_surface_damage_buffer(bubble_surface, 0, 0, BUBBLE_MAX_W, BUBBLE_MAX_H);
	wl_surface_commit(bubble_surface);
	speaking = 1;
	speech_ms = 0;
}

static void hide_bubble(void)
{
	if (!bubble_surface || !speaking) { return; }
	if (bubble_pixels) {
		for (int i = 0; i < BUBBLE_MAX_W * BUBBLE_MAX_H; i++) { bubble_pixels[i] = 0; }
	}
	wl_surface_attach(bubble_surface, bubble_buffer, 0, 0);
	wl_surface_damage_buffer(bubble_surface, 0, 0, BUBBLE_MAX_W, BUBBLE_MAX_H);
	wl_surface_commit(bubble_surface);
	speaking = 0;
}

/* ------------------------------------------------------------------ notification card */
static void render_card(const char *text)
{
	if (!notif_pixels) { return; }
	for (int i = 0; i < NOTIF_MAX_W * NOTIF_MAX_H; i++) { notif_pixels[i] = 0; }

	cairo_surface_t *cs = cairo_image_surface_create_for_data(
		(unsigned char *)notif_pixels, CAIRO_FORMAT_ARGB32,
		NOTIF_MAX_W, NOTIF_MAX_H, NOTIF_MAX_W * 4);
	cairo_t *cr = cairo_create(cs);

	const int pad = 14;
	PangoLayout *layout = pango_cairo_create_layout(cr);
	PangoFontDescription *fd = pango_font_description_from_string(NOTIF_FONT);
	pango_layout_set_font_description(layout, fd);
	pango_layout_set_width(layout, (NOTIF_MAX_W - 2 * pad) * PANGO_SCALE);
	pango_layout_set_wrap(layout, PANGO_WRAP_WORD_CHAR);
	pango_layout_set_text(layout, text, -1);
	int tw = 0, th = 0;
	pango_layout_get_pixel_size(layout, &tw, &th);

	card_w = tw + 2 * pad;
	card_h = th + 2 * pad;
	if (card_w > NOTIF_MAX_W) { card_w = NOTIF_MAX_W; }
	if (card_h > NOTIF_MAX_H) { card_h = NOTIF_MAX_H; }

	int right = (NOTIF_CORNER == 0 || NOTIF_CORNER == 2);
	int bottom = (NOTIF_CORNER == 2 || NOTIF_CORNER == 3);
	double x = right ? (NOTIF_MAX_W - card_w) : 0;
	double y = bottom ? (NOTIF_MAX_H - card_h) : 0;
	double w = card_w, h = card_h, r = 12;

	cairo_new_path(cr);
	cairo_arc(cr, x + w - r, y + r,     r, -1.5708, 0);
	cairo_arc(cr, x + w - r, y + h - r, r, 0, 1.5708);
	cairo_arc(cr, x + r,     y + h - r, r, 1.5708, 3.14159);
	cairo_arc(cr, x + r,     y + r,     r, 3.14159, 4.71239);
	cairo_close_path(cr);
	cairo_set_source_rgba(cr, 0.10, 0.12, 0.13, 0.95);   /* charcoal card */
	cairo_fill_preserve(cr);
	cairo_set_source_rgba(cr, 0.18, 0.63, 0.59, 0.95);   /* teal edge (Hiedi accent) */
	cairo_set_line_width(cr, 1.5);
	cairo_stroke(cr);

	cairo_set_source_rgba(cr, 0.95, 0.96, 0.96, 1.0);
	cairo_move_to(cr, x + pad, y + pad);
	pango_cairo_show_layout(cr, layout);

	g_object_unref(layout);
	pango_font_description_free(fd);
	cairo_destroy(cr);
	cairo_surface_flush(cs);
	cairo_surface_destroy(cs);
}

static void show_card(const char *text)
{
	if (!notif_ls || !notif_configured || !notif_buffer) { return; }
	render_card(text);
	int right = (NOTIF_CORNER == 0 || NOTIF_CORNER == 2);
	int bottom = (NOTIF_CORNER == 2 || NOTIF_CORNER == 3);
	zwlr_layer_surface_v1_set_margin(notif_ls,
		bottom ? 0 : NOTIF_MARGIN, right ? NOTIF_MARGIN : 0,
		bottom ? NOTIF_MARGIN : 0, right ? 0 : NOTIF_MARGIN);
	wl_surface_attach(notif_surface, notif_buffer, 0, 0);
	wl_surface_damage_buffer(notif_surface, 0, 0, NOTIF_MAX_W, NOTIF_MAX_H);
	wl_surface_commit(notif_surface);

	int surf_x = right ? (logical_w() - NOTIF_MAX_W - NOTIF_MARGIN) : NOTIF_MARGIN;
	int surf_y = bottom ? (logical_h() - NOTIF_MAX_H - NOTIF_MARGIN) : NOTIF_MARGIN;
	card_screen_x = surf_x + (right ? (NOTIF_MAX_W - card_w) : 0);
	card_screen_y = surf_y + (bottom ? (NOTIF_MAX_H - card_h) : 0);
}

static void hide_card(void)
{
	if (!notif_surface) { return; }
	if (notif_pixels) {
		for (int i = 0; i < NOTIF_MAX_W * NOTIF_MAX_H; i++) { notif_pixels[i] = 0; }
	}
	wl_surface_attach(notif_surface, notif_buffer, 0, 0);
	wl_surface_damage_buffer(notif_surface, 0, 0, NOTIF_MAX_W, NOTIF_MAX_H);
	wl_surface_commit(notif_surface);
}

/* ------------------------------------------------------------------ rendering */
static void draw_current(void)
{
	if (!configured) { return; }
	if (hidden && nphase == NF_NONE) { return; }   /* delivering a notification overrides hide */
	/* position via layer-shell margins (anchor TOP|LEFT) */
	zwlr_layer_surface_v1_set_margin(layer_surface, (int)(pos_y + 0.5), 0, 0,
	                                 (int)(pos_x + 0.5));
	struct anim *a = &anims[cur_state];
	if (a->n_frames == 0) { a = &anims[0]; cur_frame = 0; }
	if (cur_frame >= a->n_frames) { cur_frame = 0; }
	wl_surface_attach(surface, a->frames[cur_frame], 0, 0);
	wl_surface_damage_buffer(surface, 0, 0, sprite_w, sprite_h);
	wl_surface_commit(surface);
}

static void pick_next_target(void)
{
	int maxx = logical_w() - sprite_w - WANDER_MARGIN;
	int maxy = logical_h() - sprite_h - WANDER_MARGIN;
	if (maxx < WANDER_MARGIN) { maxx = WANDER_MARGIN; }
	if (maxy < WANDER_MARGIN) { maxy = WANDER_MARGIN; }

	if (away) {
		/* screensaver: roam the whole screen */
		tgt_x = WANDER_MARGIN + rand() % (maxx - WANDER_MARGIN + 1);
		tgt_y = WANDER_MARGIN + rand() % (maxy - WANDER_MARGIN + 1);
	} else if (rand() % 100 < 60) {
		/* usually trot home to the perch */
		tgt_x = perch_x();
		tgt_y = PET_TOP_MARGIN;
	} else {
		/* occasionally take a short walkabout near home, then come back */
		int hx = perch_x();
		tgt_x = clampi(hx - 320 + rand() % 640, WANDER_MARGIN, maxx);
		tgt_y = clampi(PET_TOP_MARGIN + rand() % 220, WANDER_MARGIN, maxy);
	}
	have_target = 1;
}

/* step toward the target; clears have_target on arrival; returns the walk state */
static int step_toward_target(void)
{
	double dx = tgt_x - pos_x, dy = tgt_y - pos_y;
	double d2 = dx * dx + dy * dy;
	if (d2 < (double)PET_SPEED * PET_SPEED) {
		pos_x = tgt_x; pos_y = tgt_y;
		have_target = 0;
		return IDX_IDLE;
	}
	double d = sqrt(d2);
	pos_x += PET_SPEED * dx / d;
	pos_y += PET_SPEED * dy / d;
	if (fabs(dx) > fabs(dy)) { return dx > 0 ? IDX_WE : IDX_WW; }
	return dy > 0 ? IDX_WS : IDX_WN;
}

/* kick off the notification choreography: show the card, teleport off, run in */
static void start_notification(const char *text)
{
	show_card(text);
	int right = (NOTIF_CORNER == 0 || NOTIF_CORNER == 2);
	came_from_right = right;
	int under_y = card_screen_y + card_h + 12;
	if (under_y > logical_h() - sprite_h) { under_y = logical_h() - sprite_h; }
	pos_x = right ? logical_w() : -sprite_w;         /* teleport just off that edge */
	pos_y = under_y;
	tgt_x = card_screen_x + card_w / 2 - sprite_w / 2;   /* under the card */
	tgt_y = under_y;
	have_target = 1;
	nphase = NF_RUN_IN;
	emote_ms = 0;
}

/* drive the choreography; returns the animation state to show */
static int notif_tick(void)
{
	switch (nphase) {
	case NF_RUN_IN:
		if (have_target) {
			int ws = step_toward_target();
			if (!have_target) { nphase = NF_EMOTE; emote_ms = 0; }
			return ws;
		}
		nphase = NF_EMOTE; emote_ms = 0;
		return IDX_HAPPY;
	case NF_EMOTE:
		emote_ms += FRAME_DURATION_MS;
		if (emote_ms >= EMOTE_MS) {           /* emote over = message over */
			hide_card();
			if (hidden) {                     /* fullscreen mode: leave the way she came */
				tgt_x = came_from_right ? logical_w() : -sprite_w;
			} else {                          /* normal: back to the perch */
				tgt_x = perch_x();
				tgt_y = PET_TOP_MARGIN;
			}
			have_target = 1;
			nphase = NF_RUN_BACK;
		}
		return IDX_HAPPY;
	case NF_RUN_BACK: {
		int ws = step_toward_target();
		if (!have_target) { nphase = NF_NONE; wander_wait_ms = 1500; }
		return ws;
	}
	default:
		return IDX_IDLE;
	}
}

static void tick(void)
{
	if (speaking) {
		speech_ms += FRAME_DURATION_MS;
		if (speech_ms >= speech_ttl) { hide_bubble(); }
	}

	if (nphase != NF_NONE) {            /* notification choreography owns movement */
		cur_state = notif_tick();
	} else if (wander_wait_ms > 0) {    /* resting at a spot */
		wander_wait_ms -= FRAME_DURATION_MS;
		cur_state = IDX_IDLE;
	} else if (have_target) {           /* walking toward it */
		cur_state = step_toward_target();
		if (!have_target) {            /* just arrived → rest, longer at home */
			wander_wait_ms = away ? (2000 + rand() % 4000) : (5000 + rand() % 9000);
		}
	} else {                           /* rested → decide where to go next */
		pick_next_target();
		cur_state = IDX_IDLE;
	}

	struct anim *a = &anims[cur_state];
	if (a->n_frames > 0) { cur_frame = (cur_frame + 1) % a->n_frames; }
	draw_current();
}

static int state_index(const char *name)
{
	for (int i = 0; i < N_STATES; i++) {
		if (strcmp(STATE_NAMES[i], name) == 0) { return i; }
	}
	return -1;
}

static void set_mood(const char *mood)
{
	int idx = -1;
	if (strcmp(mood, "happy") == 0)         { idx = state_index("happy"); }
	else if (strcmp(mood, "sleeping") == 0) { idx = state_index("sleeping"); }
	else if (strcmp(mood, "idle") == 0)     { idx = state_index("idle"); }
	if (idx >= 0 && anims[idx].n_frames > 0) {
		cur_state = idx;
		cur_frame = 0;
		draw_current();
	}
}

/* ------------------------------------------------------------------ control FIFO */
static void open_ctrl(void)
{
	if (PET_CTRL_FIFO[0]) {
		snprintf(ctrl_path, sizeof(ctrl_path), "%s", PET_CTRL_FIFO);
	} else {
		const char *rt = getenv("XDG_RUNTIME_DIR");
		if (rt && rt[0]) { snprintf(ctrl_path, sizeof(ctrl_path), "%s/hiedi-pet.ctl", rt); }
		else { snprintf(ctrl_path, sizeof(ctrl_path), "/tmp/hiedi-pet-%u.ctl", (unsigned)getuid()); }
	}
	if (mkfifo(ctrl_path, 0600) != 0 && errno != EEXIST) {
		fprintf(stderr, "helm-pet: mkfifo %s: %s\n", ctrl_path, strerror(errno));
		return;
	}
	ctrl_fd = open(ctrl_path, O_RDWR | O_NONBLOCK);
	if (ctrl_fd >= 0) { fprintf(stderr, "helm-pet: control channel: %s\n", ctrl_path); }
}

static void handle_ctrl_line(char *line)
{
	while (*line == ' ' || *line == '\t') { line++; }
	size_t end = strlen(line);
	while (end > 0 && (line[end-1] == ' ' || line[end-1] == '\t' || line[end-1] == '\r')) {
		line[--end] = '\0';
	}
	if (!*line) { return; }
	char *arg = line;
	while (*arg && *arg != ' ') { arg++; }
	if (*arg) { *arg++ = '\0'; while (*arg == ' ') { arg++; } }

	if (strcmp(line, "mood") == 0)        { set_mood(arg); }
	else if (strcmp(line, "say") == 0)    { show_bubble(arg); }
	else if (strcmp(line, "notify") == 0) { start_notification(arg); }
	else if (strcmp(line, "quit") == 0)   { running = 0; }
}

static void emit_event(const char *evt)
{
	if (!evt_path[0]) { return; }
	int fd = open(evt_path, O_WRONLY | O_NONBLOCK);   /* drop if no brain listening */
	if (fd < 0) { return; }
	char line[128];
	int n = snprintf(line, sizeof(line), "%s\n", evt);
	if (n > 0) { ssize_t w = write(fd, line, (size_t)n); (void)w; }
	close(fd);
}

static void drain_ctrl(void)
{
	if (ctrl_fd < 0) { return; }
	static char acc[1024];
	static size_t len = 0;
	char tmp[512];
	ssize_t n;
	while ((n = read(ctrl_fd, tmp, sizeof(tmp))) > 0) {
		for (ssize_t i = 0; i < n; i++) {
			if (tmp[i] == '\n') { acc[len] = '\0'; handle_ctrl_line(acc); len = 0; }
			else if (len < sizeof(acc) - 1) { acc[len++] = (char)tmp[i]; }
		}
	}
}

/* ------------------------------------------------------------------ window awareness */
/* Watch every toplevel via wlr-foreign-toplevel-management; when the focused
 * window is fullscreen or maximized, get out of the way (hide) until it clears. */
static struct zwlr_foreign_toplevel_manager_v1 *ftl_manager;

struct toplevel {
	struct zwlr_foreign_toplevel_handle_v1 *h;
	int activated, maximized, fullscreen, minimized, used;
};
#define MAX_TOPLEVELS 64
static struct toplevel toplevels[MAX_TOPLEVELS];

static void set_hidden(int h)
{
	if (h == hidden) { return; }
	hidden = h;
	fprintf(stderr, "helm-pet: %s\n",
		hidden ? "hiding — focused window is fullscreen/maximized" : "showing");
	if (hidden) {
		/* attach a transparent buffer rather than NULL: unmapping a layer surface
		 * would require a fresh configure before the next attach (protocol error). */
		if (configured && blank_pet) {
			wl_surface_attach(surface, blank_pet, 0, 0);
			wl_surface_damage_buffer(surface, 0, 0, sprite_w, sprite_h);
			wl_surface_commit(surface);
		}
	} else {
		draw_current();                               /* reappear at current frame */
	}
}

static void recompute_hidden(void)
{
	int hide = 0;
	for (int i = 0; i < MAX_TOPLEVELS; i++) {
		struct toplevel *t = &toplevels[i];
		if (t->used && t->activated && !t->minimized &&
		    (t->fullscreen || t->maximized)) {
			hide = 1;
			break;
		}
	}
	set_hidden(hide);
}

static struct toplevel *toplevel_find(struct zwlr_foreign_toplevel_handle_v1 *h)
{
	for (int i = 0; i < MAX_TOPLEVELS; i++) {
		if (toplevels[i].used && toplevels[i].h == h) { return &toplevels[i]; }
	}
	return NULL;
}

/* handle events */
static void tl_title(void *d, struct zwlr_foreign_toplevel_handle_v1 *h, const char *t)
{ (void)d; (void)h; (void)t; }
static void tl_app_id(void *d, struct zwlr_foreign_toplevel_handle_v1 *h, const char *a)
{ (void)d; (void)h; (void)a; }
static void tl_output_enter(void *d, struct zwlr_foreign_toplevel_handle_v1 *h, struct wl_output *o)
{ (void)d; (void)h; (void)o; }
static void tl_output_leave(void *d, struct zwlr_foreign_toplevel_handle_v1 *h, struct wl_output *o)
{ (void)d; (void)h; (void)o; }
static void tl_parent(void *d, struct zwlr_foreign_toplevel_handle_v1 *h,
                      struct zwlr_foreign_toplevel_handle_v1 *p)
{ (void)d; (void)h; (void)p; }

static void tl_state(void *d, struct zwlr_foreign_toplevel_handle_v1 *h, struct wl_array *state)
{
	(void)d;
	struct toplevel *t = toplevel_find(h);
	if (!t) { return; }
	t->activated = t->maximized = t->fullscreen = t->minimized = 0;
	uint32_t *s;
	wl_array_for_each(s, state) {
		switch (*s) {
		case ZWLR_FOREIGN_TOPLEVEL_HANDLE_V1_STATE_MAXIMIZED:  t->maximized = 1;  break;
		case ZWLR_FOREIGN_TOPLEVEL_HANDLE_V1_STATE_MINIMIZED:  t->minimized = 1;  break;
		case ZWLR_FOREIGN_TOPLEVEL_HANDLE_V1_STATE_ACTIVATED:  t->activated = 1;  break;
		case ZWLR_FOREIGN_TOPLEVEL_HANDLE_V1_STATE_FULLSCREEN: t->fullscreen = 1; break;
		default: break;
		}
	}
}

static void tl_done(void *d, struct zwlr_foreign_toplevel_handle_v1 *h)
{ (void)d; (void)h; recompute_hidden(); }

static void tl_closed(void *d, struct zwlr_foreign_toplevel_handle_v1 *h)
{
	(void)d;
	struct toplevel *t = toplevel_find(h);
	if (t) { t->used = 0; t->h = NULL; }
	zwlr_foreign_toplevel_handle_v1_destroy(h);
	recompute_hidden();
}

static const struct zwlr_foreign_toplevel_handle_v1_listener tl_listener = {
	.title = tl_title, .app_id = tl_app_id,
	.output_enter = tl_output_enter, .output_leave = tl_output_leave,
	.state = tl_state, .done = tl_done, .closed = tl_closed, .parent = tl_parent,
};

static void mgr_toplevel(void *d, struct zwlr_foreign_toplevel_manager_v1 *m,
                         struct zwlr_foreign_toplevel_handle_v1 *h)
{
	(void)d; (void)m;
	for (int i = 0; i < MAX_TOPLEVELS; i++) {
		if (!toplevels[i].used) {
			toplevels[i] = (struct toplevel){ .h = h, .used = 1 };
			zwlr_foreign_toplevel_handle_v1_add_listener(h, &tl_listener, NULL);
			return;
		}
	}
}
static void mgr_finished(void *d, struct zwlr_foreign_toplevel_manager_v1 *m)
{ (void)d; (void)m; }

static const struct zwlr_foreign_toplevel_manager_v1_listener mgr_listener = {
	.toplevel = mgr_toplevel, .finished = mgr_finished,
};

/* ------------------------------------------------------------------ layer surface */
static void ls_configure(void *data, struct zwlr_layer_surface_v1 *ls,
                         uint32_t serial, uint32_t w, uint32_t h)
{
	(void)data; (void)w; (void)h;
	zwlr_layer_surface_v1_ack_configure(ls, serial);
	configured = 1;
	draw_current();
}
static void ls_closed(void *data, struct zwlr_layer_surface_v1 *ls)
{
	(void)data; (void)ls;
	running = 0;
}
static const struct zwlr_layer_surface_v1_listener ls_listener = {
	.configure = ls_configure,
	.closed = ls_closed,
};

static void bls_configure(void *data, struct zwlr_layer_surface_v1 *ls,
                          uint32_t serial, uint32_t w, uint32_t h)
{
	(void)data; (void)w; (void)h;
	zwlr_layer_surface_v1_ack_configure(ls, serial);
	bubble_configured = 1;
}
static void bls_closed(void *data, struct zwlr_layer_surface_v1 *ls)
{ (void)data; (void)ls; }
static const struct zwlr_layer_surface_v1_listener bls_listener = {
	.configure = bls_configure,
	.closed = bls_closed,
};

static void nls_configure(void *data, struct zwlr_layer_surface_v1 *ls,
                          uint32_t serial, uint32_t w, uint32_t h)
{
	(void)data; (void)w; (void)h;
	zwlr_layer_surface_v1_ack_configure(ls, serial);
	notif_configured = 1;
}
static const struct zwlr_layer_surface_v1_listener nls_listener = {
	.configure = nls_configure,
	.closed = bls_closed,
};

/* ------------------------------------------------------------------ output */
static void out_geometry(void *d, struct wl_output *o, int32_t x, int32_t y,
                         int32_t pw, int32_t ph, int32_t sp, const char *make,
                         const char *model, int32_t transform)
{ (void)d; (void)o; (void)x; (void)y; (void)pw; (void)ph; (void)sp; (void)make;
  (void)model; (void)transform; }
static void out_mode(void *d, struct wl_output *o, uint32_t flags,
                     int32_t w, int32_t h, int32_t refresh)
{ (void)d; (void)o; (void)refresh;
  if (flags & WL_OUTPUT_MODE_CURRENT) { out_w = w; out_h = h; } }
static void out_done(void *d, struct wl_output *o) { (void)d; (void)o; }
static void out_scale_cb(void *d, struct wl_output *o, int32_t f)
{ (void)d; (void)o; if (f > 0) { out_scale = f; } }
static void out_name(void *d, struct wl_output *o, const char *n)
{ (void)d; (void)o; (void)n; }
static void out_description(void *d, struct wl_output *o, const char *n)
{ (void)d; (void)o; (void)n; }
static const struct wl_output_listener out_listener = {
	.geometry = out_geometry, .mode = out_mode, .done = out_done,
	.scale = out_scale_cb, .name = out_name, .description = out_description,
};

/* ------------------------------------------------------------------ idle */
static void idle_idled(void *d, struct ext_idle_notification_v1 *n)
{
	(void)d; (void)n;
	away = 1;
	have_target = 0;
	wander_wait_ms = 0;
	fprintf(stderr, "helm-pet: away → free to roam\n");
}
static void idle_resumed(void *d, struct ext_idle_notification_v1 *n)
{
	(void)d; (void)n;
	away = 0;
	have_target = 0;       /* re-pick immediately → trot home */
	wander_wait_ms = 0;
	fprintf(stderr, "helm-pet: back → returning to perch\n");
}
static const struct ext_idle_notification_v1_listener idle_listener = {
	.idled = idle_idled, .resumed = idle_resumed,
};

/* ------------------------------------------------------------------ pointer (poke) */
static void ptr_enter(void *d, struct wl_pointer *p, uint32_t s, struct wl_surface *sf,
                      wl_fixed_t x, wl_fixed_t y)
{ (void)d; (void)p; (void)s; (void)sf; (void)x; (void)y; }
static void ptr_leave(void *d, struct wl_pointer *p, uint32_t s, struct wl_surface *sf)
{ (void)d; (void)p; (void)s; (void)sf; }
static void ptr_motion(void *d, struct wl_pointer *p, uint32_t t, wl_fixed_t x, wl_fixed_t y)
{ (void)d; (void)p; (void)t; (void)x; (void)y; }
static void ptr_button(void *d, struct wl_pointer *p, uint32_t serial, uint32_t time,
                       uint32_t button, uint32_t state)
{
	(void)d; (void)p; (void)serial; (void)time;
	if (button == BTN_LEFT && state == WL_POINTER_BUTTON_STATE_PRESSED) {
		emit_event("poke");   /* clicked → summon Hiedi through the bridge */
	}
}
static void ptr_axis(void *d, struct wl_pointer *p, uint32_t t, uint32_t a, wl_fixed_t v)
{ (void)d; (void)p; (void)t; (void)a; (void)v; }
static void ptr_frame(void *d, struct wl_pointer *p) { (void)d; (void)p; }
static void ptr_axis_source(void *d, struct wl_pointer *p, uint32_t s) { (void)d; (void)p; (void)s; }
static void ptr_axis_stop(void *d, struct wl_pointer *p, uint32_t t, uint32_t a)
{ (void)d; (void)p; (void)t; (void)a; }
static void ptr_axis_discrete(void *d, struct wl_pointer *p, uint32_t a, int32_t dsc)
{ (void)d; (void)p; (void)a; (void)dsc; }
static void ptr_axis_value120(void *d, struct wl_pointer *p, uint32_t a, int32_t v)
{ (void)d; (void)p; (void)a; (void)v; }
static void ptr_axis_rel_dir(void *d, struct wl_pointer *p, uint32_t a, uint32_t dir)
{ (void)d; (void)p; (void)a; (void)dir; }
static void ptr_warp(void *d, struct wl_pointer *p, wl_fixed_t x, wl_fixed_t y)
{ (void)d; (void)p; (void)x; (void)y; }
static const struct wl_pointer_listener ptr_listener = {
	.enter = ptr_enter, .leave = ptr_leave, .motion = ptr_motion, .button = ptr_button,
	.axis = ptr_axis, .frame = ptr_frame, .axis_source = ptr_axis_source,
	.axis_stop = ptr_axis_stop, .axis_discrete = ptr_axis_discrete,
	.axis_value120 = ptr_axis_value120, .axis_relative_direction = ptr_axis_rel_dir,
	.warp = ptr_warp,
};

static void seat_caps(void *d, struct wl_seat *s, uint32_t caps)
{
	(void)d;
	if ((caps & WL_SEAT_CAPABILITY_POINTER) && !pointer) {
		pointer = wl_seat_get_pointer(s);
		wl_pointer_add_listener(pointer, &ptr_listener, NULL);
	}
}
static void seat_name(void *d, struct wl_seat *s, const char *n)
{ (void)d; (void)s; (void)n; }
static const struct wl_seat_listener seat_listener = {
	.capabilities = seat_caps, .name = seat_name,
};

/* ------------------------------------------------------------------ registry */
static void reg_global(void *data, struct wl_registry *reg, uint32_t name,
                       const char *iface, uint32_t ver)
{
	(void)data; (void)ver;
	if (strcmp(iface, wl_compositor_interface.name) == 0) {
		compositor = wl_registry_bind(reg, name, &wl_compositor_interface, 4);
	} else if (strcmp(iface, wl_shm_interface.name) == 0) {
		shm = wl_registry_bind(reg, name, &wl_shm_interface, 1);
	} else if (strcmp(iface, zwlr_layer_shell_v1_interface.name) == 0) {
		layer_shell = wl_registry_bind(reg, name, &zwlr_layer_shell_v1_interface, 1);
	} else if (strcmp(iface, zwlr_foreign_toplevel_manager_v1_interface.name) == 0) {
		/* v2+ carries the fullscreen state we key off */
		uint32_t v = ver < 3 ? ver : 3;
		ftl_manager = wl_registry_bind(reg, name,
			&zwlr_foreign_toplevel_manager_v1_interface, v);
		zwlr_foreign_toplevel_manager_v1_add_listener(ftl_manager, &mgr_listener, NULL);
	} else if (strcmp(iface, wl_output_interface.name) == 0) {
		if (!output) {
			output = wl_registry_bind(reg, name, &wl_output_interface, 2);
			wl_output_add_listener(output, &out_listener, NULL);
		}
	} else if (strcmp(iface, wl_seat_interface.name) == 0) {
		if (!seat) {
			uint32_t v = ver < 5 ? ver : 5;
			seat = wl_registry_bind(reg, name, &wl_seat_interface, v);
			wl_seat_add_listener(seat, &seat_listener, NULL);
		}
	} else if (strcmp(iface, ext_idle_notifier_v1_interface.name) == 0) {
		idle_notifier = wl_registry_bind(reg, name, &ext_idle_notifier_v1_interface, 1);
	}
}
static void reg_remove(void *data, struct wl_registry *reg, uint32_t name)
{
	(void)data; (void)reg; (void)name;
}
static const struct wl_registry_listener reg_listener = {
	.global = reg_global,
	.global_remove = reg_remove,
};

/* ------------------------------------------------------------------ main */
int main(void)
{
	display = wl_display_connect(NULL);
	if (!display) { fprintf(stderr, "helm-pet: no Wayland display\n"); return 1; }

	struct wl_registry *reg = wl_display_get_registry(display);
	wl_registry_add_listener(reg, &reg_listener, NULL);
	wl_display_roundtrip(display);   /* bind globals */
	wl_display_roundtrip(display);   /* receive output mode/scale + initial toplevels */

	if (!compositor || !shm || !layer_shell) {
		fprintf(stderr, "helm-pet: compositor lacks wlr-layer-shell (need a wlroots compositor)\n");
		return 1;
	}
	if (load_skin() != 0) { return 1; }
	fprintf(stderr, "helm-pet: window-awareness %s\n",
		ftl_manager ? "ON (wlr-foreign-toplevel)" : "OFF — compositor lacks foreign-toplevel");

	IDX_IDLE = state_index("idle");
	IDX_WE = state_index("walk_east");  IDX_WW = state_index("walk_west");
	IDX_WN = state_index("walk_north"); IDX_WS = state_index("walk_south");
	IDX_HAPPY = state_index("happy");
	if (IDX_IDLE < 0) { IDX_IDLE = 0; }
	if (IDX_HAPPY < 0) { IDX_HAPPY = IDX_IDLE; }
	if (IDX_WE < 0) { IDX_WE = IDX_IDLE; }  if (IDX_WW < 0) { IDX_WW = IDX_IDLE; }
	if (IDX_WN < 0) { IDX_WN = IDX_IDLE; }  if (IDX_WS < 0) { IDX_WS = IDX_IDLE; }
	srand((unsigned)time(NULL));
	pos_x = perch_x();
	pos_y = PET_TOP_MARGIN;

	surface = wl_compositor_create_surface(compositor);
	/* default input region = the whole (small) surface → the pet is clickable;
	 * clicks elsewhere on screen are unaffected (they're outside our surface) */

	layer_surface = zwlr_layer_shell_v1_get_layer_surface(
		layer_shell, surface, NULL, ZWLR_LAYER_SHELL_V1_LAYER_OVERLAY, "hiedi-pet");
	zwlr_layer_surface_v1_add_listener(layer_surface, &ls_listener, NULL);
	zwlr_layer_surface_v1_set_size(layer_surface, sprite_w, sprite_h);
	/* anchor TOP|LEFT → margins are an absolute (x, y) we drive to move the pet */
	zwlr_layer_surface_v1_set_anchor(layer_surface,
		ZWLR_LAYER_SURFACE_V1_ANCHOR_TOP | ZWLR_LAYER_SURFACE_V1_ANCHOR_LEFT);
	zwlr_layer_surface_v1_set_margin(layer_surface, (int)pos_y, 0, 0, (int)pos_x);
	zwlr_layer_surface_v1_set_keyboard_interactivity(layer_surface, 0);
	/* -1: reserve no space and don't act as a layout/snap edge for windows */
	zwlr_layer_surface_v1_set_exclusive_zone(layer_surface, -1);
	wl_surface_commit(surface);

	/* speech bubble surface (a second, click-through overlay, unmapped until a say) */
	bubble_surface = wl_compositor_create_surface(compositor);
	struct wl_region *br = wl_compositor_create_region(compositor);
	wl_surface_set_input_region(bubble_surface, br);
	wl_region_destroy(br);
	bubble_ls = zwlr_layer_shell_v1_get_layer_surface(
		layer_shell, bubble_surface, NULL, ZWLR_LAYER_SHELL_V1_LAYER_OVERLAY,
		"hiedi-pet-bubble");
	zwlr_layer_surface_v1_add_listener(bubble_ls, &bls_listener, NULL);
	zwlr_layer_surface_v1_set_size(bubble_ls, BUBBLE_MAX_W, BUBBLE_MAX_H);
	zwlr_layer_surface_v1_set_anchor(bubble_ls,
		ZWLR_LAYER_SURFACE_V1_ANCHOR_TOP | ZWLR_LAYER_SURFACE_V1_ANCHOR_LEFT);
	zwlr_layer_surface_v1_set_keyboard_interactivity(bubble_ls, 0);
	zwlr_layer_surface_v1_set_exclusive_zone(bubble_ls, -1);
	wl_surface_commit(bubble_surface);   /* configures but stays unmapped (no buffer) */
	bubble_buffer = make_buffer(BUBBLE_MAX_W, BUBBLE_MAX_H, &bubble_pixels);
	{ uint32_t *bp; blank_pet = make_buffer(sprite_w, sprite_h, &bp); }  /* zeroed = transparent */

	/* notification card surface (readable cairo/pango text, corner-anchored, click-through) */
	notif_surface = wl_compositor_create_surface(compositor);
	struct wl_region *nr = wl_compositor_create_region(compositor);
	wl_surface_set_input_region(notif_surface, nr);
	wl_region_destroy(nr);
	notif_ls = zwlr_layer_shell_v1_get_layer_surface(
		layer_shell, notif_surface, NULL, ZWLR_LAYER_SHELL_V1_LAYER_OVERLAY,
		"hiedi-pet-notif");
	zwlr_layer_surface_v1_add_listener(notif_ls, &nls_listener, NULL);
	zwlr_layer_surface_v1_set_size(notif_ls, NOTIF_MAX_W, NOTIF_MAX_H);
	{
		int right = (NOTIF_CORNER == 0 || NOTIF_CORNER == 2);
		int bottom = (NOTIF_CORNER == 2 || NOTIF_CORNER == 3);
		uint32_t anchor = (bottom ? ZWLR_LAYER_SURFACE_V1_ANCHOR_BOTTOM
		                          : ZWLR_LAYER_SURFACE_V1_ANCHOR_TOP)
		                | (right ? ZWLR_LAYER_SURFACE_V1_ANCHOR_RIGHT
		                         : ZWLR_LAYER_SURFACE_V1_ANCHOR_LEFT);
		zwlr_layer_surface_v1_set_anchor(notif_ls, anchor);
	}
	zwlr_layer_surface_v1_set_keyboard_interactivity(notif_ls, 0);
	zwlr_layer_surface_v1_set_exclusive_zone(notif_ls, -1);
	wl_surface_commit(notif_surface);
	notif_buffer = make_buffer(NOTIF_MAX_W, NOTIF_MAX_H, &notif_pixels);

	wl_display_roundtrip(display);       /* all surfaces configured before any say/notify */

	open_ctrl();
	{
		const char *rt = getenv("XDG_RUNTIME_DIR");
		if (rt && rt[0]) { snprintf(evt_path, sizeof(evt_path), "%s/hiedi-pet.evt", rt); }
		else { snprintf(evt_path, sizeof(evt_path), "/tmp/hiedi-pet-%u.evt", (unsigned)getuid()); }
	}

	if (idle_notifier && seat) {
		idle_notification = ext_idle_notifier_v1_get_idle_notification(
			idle_notifier, PET_AWAY_MS, seat);
		ext_idle_notification_v1_add_listener(idle_notification, &idle_listener, NULL);
		fprintf(stderr, "helm-pet: idle-awareness ON — roam after %ds away\n",
			PET_AWAY_MS / 1000);
	} else {
		fprintf(stderr, "helm-pet: idle-awareness OFF (no ext-idle-notify) — always perched\n");
	}

	/* animation timer */
	int timer_fd = timerfd_create(CLOCK_MONOTONIC, TFD_NONBLOCK | TFD_CLOEXEC);
	struct itimerspec its = {
		.it_interval = { .tv_sec = 0, .tv_nsec = FRAME_DURATION_MS * 1000000L },
		.it_value    = { .tv_sec = 0, .tv_nsec = FRAME_DURATION_MS * 1000000L },
	};
	timerfd_settime(timer_fd, 0, &its, NULL);

	int wl_fd = wl_display_get_fd(display);
	while (running) {
		while (wl_display_prepare_read(display) != 0) {
			wl_display_dispatch_pending(display);
		}
		wl_display_flush(display);

		struct pollfd pfds[3] = {
			{ .fd = wl_fd, .events = POLLIN },
			{ .fd = timer_fd, .events = POLLIN },
			{ .fd = ctrl_fd, .events = POLLIN },
		};
		int nf = (ctrl_fd >= 0) ? 3 : 2;
		if (poll(pfds, nf, -1) < 0) { wl_display_cancel_read(display); break; }

		if (pfds[0].revents & POLLIN) { wl_display_read_events(display); }
		else { wl_display_cancel_read(display); }
		wl_display_dispatch_pending(display);

		if (pfds[1].revents & POLLIN) {
			uint64_t exp; ssize_t r = read(timer_fd, &exp, sizeof(exp)); (void)r;
			tick();
		}
		if (nf == 3 && (pfds[2].revents & POLLIN)) { drain_ctrl(); }
	}

	if (ctrl_fd >= 0) { close(ctrl_fd); unlink(ctrl_path); }
	wl_display_disconnect(display);
	return 0;
}
