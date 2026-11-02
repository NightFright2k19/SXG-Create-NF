// testhost_linux.c - minimal Linux CLAP host (X11) for testing the Linux bridge:  testhost_linux <plugin.clap> [real]
// 'real': the plugin is one of the S-YXG DLLs, only load / activate / process / editor / state are checked.
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdlib.h>
#include <unistd.h>
#include <xcb/xcb.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#include "../clap/clap.h"

static int fails;
#define CHECK(c, ...) do { if (!(c)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); fails++; } else { printf("ok:   "); printf(__VA_ARGS__); printf("\n"); } } while (0)

typedef struct { clap_input_events_t in; const clap_event_header_t* ev[16]; uint32_t n; } Events;
static uint32_t ev_size(const clap_input_events_t* l) { return ((Events*)l->ctx)->n; }
static const clap_event_header_t* ev_get(const clap_input_events_t* l, uint32_t i) { return ((Events*)l->ctx)->ev[i]; }
static void host_log(const clap_host_t* h, clap_log_severity sev, const char* msg) { (void)h; (void)sev; printf("      plugin log: %s\n", msg); }
static const clap_host_log_t ext_log = { host_log };
static const void* host_ext(const clap_host_t* h, const char* id) { (void)h; return !strcmp(id, CLAP_EXT_LOG) ? &ext_log : 0; }
static void host_noop(const clap_host_t* h) { (void)h; }

typedef struct { uint8_t buf[1 << 16]; uint32_t len, pos; } Mem;
static int64_t m_write(const clap_ostream_t* s, const void* b, uint64_t n) { Mem* m = s->ctx; memcpy(m->buf + m->len, b, n); m->len += (uint32_t)n; return (int64_t)n; }
static int64_t m_read(const clap_istream_t* s, void* b, uint64_t n) { Mem* m = s->ctx; uint64_t r = m->len - m->pos < n ? m->len - m->pos : n; memcpy(b, m->buf + m->pos, r); m->pos += (uint32_t)r; return (int64_t)r; }

static float L[2048], R[2048];
static int run(const clap_plugin_t* pl, Events* e, uint32_t frames)
{
    float* ch[2] = { L, R };
    clap_audio_buffer_t out = { ch, 0, 2, 0, 0 };
    clap_process_t pr; memset(&pr, 0, sizeof pr);
    pr.frames_count = frames; pr.audio_outputs = &out; pr.audio_outputs_count = 1; pr.in_events = &e->in;
    return pl->process(pl, &pr);
}
static float peak(int a, int b) { float p = 0; for (int i = a; i < b; i++) if (fabsf(L[i]) > p) p = fabsf(L[i]); return p; }

int main(int argc, char** argv)
{
    int real = argc > 2;
    void* m = dlopen(argv[1], RTLD_NOW);
    CHECK(m != 0, "load %s", argv[1]);
    if (!m) return 1;
    const clap_plugin_entry_t* entry = (const clap_plugin_entry_t*)dlsym(m, "clap_entry");
    CHECK(entry && entry->init(argv[1]), "entry init");
    const clap_plugin_factory_t* f = entry->get_factory(CLAP_PLUGIN_FACTORY_ID);
    const clap_plugin_descriptor_t* d = f->get_plugin_descriptor(f, 0);
    printf("      id=%s name=%s\n", d->id, d->name);
    clap_host_t host = { CLAP_VERSION_INIT, 0, "testhost", "x", "", "1", host_ext, host_noop, host_noop, host_noop };
    const clap_plugin_t* pl = f->create_plugin(f, &host, d->id);
    CHECK(pl && pl->init(pl), "plugin init");
    if (!pl) return 1;
    CHECK(pl->activate(pl, 44100, 32, 2048), "activate");
    pl->start_processing(pl);

    Events e; memset(&e, 0, sizeof e); e.in.ctx = &e; e.in.size = ev_size; e.in.get = ev_get;
    clap_event_midi_t on = { { sizeof on, 100, CLAP_CORE_EVENT_SPACE_ID, CLAP_EVENT_MIDI, 0 }, 0, { 0x90, 69, 100 } };
    e.ev[0] = &on.header; e.n = 1;
    run(pl, &e, 512);
    if (!real) {
        CHECK(peak(0, 100) == 0, "silence before the note (sample offset 100)");
        CHECK(peak(100, 512) > 0.4f, "note sounds after the offset (peak %.3f)", peak(100, 512));
        int zc = 0; for (int i = 101; i < 512; i++) if (L[i - 1] < 0 && L[i] >= 0) zc++;
        CHECK(zc >= 4 && zc <= 6, "pitch about 440 Hz (%d periods in 411 samples)", zc);
    } else printf("      peak of first block %.4f\n", peak(0, 512));

    if (!real) {
        uint8_t sx[20] = { 0xF0, 1, 2, 3, 4, 5, 6, 7, 8, 0xF7, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0 };
        clap_event_midi_sysex_t sy = { { sizeof sy, 0, CLAP_CORE_EVENT_SPACE_ID, CLAP_EVENT_MIDI_SYSEX, 0 }, 0, sx, 10 };
        e.ev[0] = &sy.header; e.n = 1; run(pl, &e, 512);
        e.n = 0; run(pl, &e, 512);
        CHECK(fabsf(peak(0, 512) - 1.0f) < 0.02f, "SysEx of 10 bytes sets gain 1.0 (peak %.3f)", peak(0, 512));
        clap_event_midi_t off = { { sizeof off, 0, CLAP_CORE_EVENT_SPACE_ID, CLAP_EVENT_MIDI, 0 }, 0, { 0x80, 69, 0 } };
        e.ev[0] = &off.header; e.n = 1; run(pl, &e, 512);
        CHECK(peak(0, 512) == 0, "note off silences");
        e.n = 0; run(pl, &e, 2048);                         // block longer than... fine, just must not crash
    }

    const clap_plugin_state_t* st = pl->get_extension(pl, CLAP_EXT_STATE);
    static Mem mem; clap_ostream_t os = { &mem, m_write }; clap_istream_t is = { &mem, m_read };
    CHECK(st && st->save(pl, &os), "state save (%u bytes)", mem.len);
    if (!real) {
        CHECK(mem.len == 12 + 8 && !memcmp(mem.buf + 12, "initial", 8), "state holds the plugin's chunk");
        memcpy(mem.buf + 12, "changed", 8);
        CHECK(st->load(pl, &is), "state load");
        static Mem m2; clap_ostream_t os2 = { &m2, m_write };
        st->save(pl, &os2);
        CHECK(!memcmp(m2.buf + 12, "changed", 8), "state round trip");
    }

    const clap_plugin_gui_t* gui = pl->get_extension(pl, CLAP_EXT_GUI);
    CHECK(gui && gui->is_api_supported(pl, CLAP_WINDOW_API_X11, false), "gui x11 supported");
    CHECK(gui->create(pl, CLAP_WINDOW_API_X11, false), "gui create");
    uint32_t w = 0, h = 0; gui->get_size(pl, &w, &h);
    printf("      editor size %u x %u\n", w, h);
    if (!real) CHECK(w == 200 && h == 100, "editor size 200 x 100");
    xcb_connection_t* xc = xcb_connect(0, 0);
    CHECK(xc && !xcb_connection_has_error(xc), "X11 connection");
    xcb_screen_t* scr = xcb_setup_roots_iterator(xcb_get_setup(xc)).data;
    xcb_window_t top = xcb_generate_id(xc);
    xcb_create_window(xc, XCB_COPY_FROM_PARENT, top, scr->root, 50, 60, (uint16_t)w, (uint16_t)h, 0, XCB_WINDOW_CLASS_INPUT_OUTPUT, scr->root_visual, 0, 0);
    xcb_map_window(xc, top); xcb_flush(xc);
    clap_window_t win = { CLAP_WINDOW_API_X11, { (void*)(uintptr_t)top } };
    CHECK(gui->set_parent(pl, &win), "gui set_parent");
    CHECK(gui->show(pl), "gui show");
    const clap_plugin_timer_support_t* ts = pl->get_extension(pl, CLAP_EXT_TIMER_SUPPORT);
    if (ts) ts->on_timer(pl, 0);
    usleep(1500000);
    xcb_query_tree_reply_t* t = xcb_query_tree_reply(xc, xcb_query_tree(xc, top), 0);
    CHECK(t && xcb_query_tree_children_length(t) >= 1, "editor window is a child of the host window (%d children)", t ? xcb_query_tree_children_length(t) : -1);
    if (t) { xcb_window_t* ch = xcb_query_tree_children(t); if (xcb_query_tree_children_length(t)) printf("      child window 0x%x\n", ch[0]); }
    if (getenv("SHOT")) { char cmd[256]; snprintf(cmd, sizeof cmd, "import -window root %s", getenv("SHOT")); int rc = system(cmd); (void)rc; }
    gui->destroy(pl);
    CHECK(1, "gui destroy");
    pl->stop_processing(pl);
    pl->deactivate(pl);
    pl->destroy(pl);
    entry->deinit();
    xcb_disconnect(xc);
    printf(fails ? "RESULT: %d failed\n" : "RESULT: all passed\n", fails);
    return fails != 0;
}
