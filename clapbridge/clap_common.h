// clap_common.h - the part of the CLAP bridge that is the same on Windows (clap_bridge.c) and Linux (clap_bridge_linux.c).
// Included by both after they have defined, in this order:
//   Inst (with clap_plugin_t plugin, const clap_host_t* host, Shared* sh, int dead, active, gui_made, gui_open, gui_w, gui_h,
//   char error[256] and what the platform needs), INST_INIT(p), and these functions:
//     command(p, cmd, a0, a1, timeout_ms)   one command to the helper, 1 = done
//     run_block(p, timeout_ms)              signal an audio block (events already in p->sh), wait; 1 = done
//     blob_lock / blob_unlock               the state blob is part of the command mailbox
//     plat_start / plat_stop                start / end the helper; plat_gui_close(p) closes an open editor
//     plat_ext(id)                          the platform's extensions (gui, ...)
//     plat_entry_path(path)                 sets g_stem8 (file name without extension, lower case) from the CLAP's path
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "clap/clap.h"
#include "protocol.h"

static char    g_id[200], g_name[128];
static clap_plugin_descriptor_t g_desc;
static const char* g_features[] = { CLAP_PLUGIN_FEATURE_INSTRUMENT, CLAP_PLUGIN_FEATURE_SYNTHESIZER, CLAP_PLUGIN_FEATURE_STEREO, 0 };

static const struct { const char* stem; const char* name; } NAMES[] = {
    { "syxg15", "S-YXG MU15" }, { "syxgmu15", "S-YXG MU15" }, { "syxgmu50", "S-YXG MU50" }, { "syxg50", "S-YXG50" },
    { "syxg80", "S-YXG MU80" }, { "syxg90", "S-YXG MU90" }, { "syxg100", "S-YXG MU100" }, { "syxg128", "S-YXG MU128" },
    { "syxg1000", "S-YXG MU1000" }, { "syxg2000", "S-YXG MU2000" }, { "syxg2006le", "S-YXG2006LE" }, { 0, 0 }
};

static void log_error(Inst* p, const char* m)
{
    if (p->host && p->host->get_extension) {
        const clap_host_log_t* l = (const clap_host_log_t*)p->host->get_extension(p->host, CLAP_EXT_LOG);
        if (l && l->log) l->log(p->host, CLAP_LOG_ERROR, m);
    }
}

static bool pl_init(const clap_plugin_t* c)
{
    Inst* p = (Inst*)c->plugin_data;
    if (!plat_start(p)) { log_error(p, p->error); plat_stop(p); p->dead = 1; return false; }
    return true;
}
static void pl_destroy(const clap_plugin_t* c)
{
    Inst* p = (Inst*)c->plugin_data;
    plat_gui_close(p);
    plat_stop(p);
    free(p);
}
static bool pl_activate(const clap_plugin_t* c, double sr, uint32_t minf, uint32_t maxf)
{
    (void)minf; (void)maxf;
    Inst* p = (Inst*)c->plugin_data;
    if (p->dead) return false;
    if (!command(p, SXG_CMD_ACTIVATE, (int)(sr + 0.5), 0, 30000)) return false;
    p->active = 1; return true;
}
static void pl_deactivate(const clap_plugin_t* c)
{
    Inst* p = (Inst*)c->plugin_data;
    if (p->active) command(p, SXG_CMD_DEACTIVATE, 0, 0, 10000);
    p->active = 0;
}
static bool pl_start(const clap_plugin_t* c) { (void)c; return true; }
static void pl_stop(const clap_plugin_t* c) { (void)c; }
static void pl_reset(const clap_plugin_t* c)
{
    // all notes off and reset controllers on every channel
    Inst* p = (Inst*)c->plugin_data;
    if (p->dead || !p->active) return;
    p->sh->frames = 0; p->sh->n_events = 0;
    uint32_t n = 0;
    for (int ch = 0; ch < 16 && n + 2 <= SXG_MAXEVENTS; ch++) {
        SxgEvent* e = &p->sh->events[n++]; memset(e, 0, sizeof *e);
        e->kind = SXG_EV_MIDI; e->data[0] = 0xB0 | ch; e->data[1] = 123; e->data[2] = 0;
        e = &p->sh->events[n++]; memset(e, 0, sizeof *e);
        e->kind = SXG_EV_MIDI; e->data[0] = 0xB0 | ch; e->data[1] = 121; e->data[2] = 0;
    }
    p->sh->n_events = n; p->sh->frames = 1;
    if (!run_block(p, 2000)) p->dead = 1;
}

static int add_midi(Inst* p, uint32_t delta, uint8_t a, uint8_t b, uint8_t c3)
{
    Shared* s = p->sh;
    if (s->n_events >= SXG_MAXEVENTS) return 0;
    SxgEvent* e = &s->events[s->n_events++];
    memset(e, 0, sizeof *e);
    e->delta = delta; e->kind = SXG_EV_MIDI; e->data[0] = a; e->data[1] = b; e->data[2] = c3;
    return 1;
}
static int add_sysex(Inst* p, uint32_t delta, const uint8_t* d, uint32_t n)
{
    Shared* s = p->sh;
    if (s->n_events >= SXG_MAXEVENTS || s->sysex_bytes + n > SXG_SYSEX_MAX) return 0;
    SxgEvent* e = &s->events[s->n_events++];
    memset(e, 0, sizeof *e);
    e->delta = delta; e->kind = SXG_EV_SYSEX; e->sysex_off = s->sysex_bytes; e->sysex_len = n;
    memcpy(s->sysex + s->sysex_bytes, d, n); s->sysex_bytes += n;
    return 1;
}

static void put_event(Inst* p, const clap_event_header_t* h, uint32_t delta)
{
    if (h->space_id != CLAP_CORE_EVENT_SPACE_ID) return;
    switch (h->type) {
    case CLAP_EVENT_MIDI: {
        const clap_event_midi_t* m = (const clap_event_midi_t*)h;
        add_midi(p, delta, m->data[0], m->data[1], m->data[2]); break;
    }
    case CLAP_EVENT_MIDI_SYSEX: {
        const clap_event_midi_sysex_t* m = (const clap_event_midi_sysex_t*)h;
        if (m->buffer && m->size) add_sysex(p, delta, m->buffer, m->size);
        break;
    }
    case CLAP_EVENT_NOTE_ON: case CLAP_EVENT_NOTE_OFF: case CLAP_EVENT_NOTE_CHOKE: {   // hosts that send the CLAP dialect anyway
        const clap_event_note_t* n = (const clap_event_note_t*)h;
        int ch = n->channel < 0 ? 0 : n->channel & 15, key = n->key & 127;
        if (h->type == CLAP_EVENT_NOTE_ON) { int v = (int)(n->velocity * 127.0 + 0.5); add_midi(p, delta, 0x90 | ch, key, v < 1 ? 1 : v > 127 ? 127 : v); }
        else add_midi(p, delta, 0x80 | ch, key, 0);
        break;
    }
    default: break;
    }
}

static clap_process_status pl_process(const clap_plugin_t* c, const clap_process_t* pr)
{
    Inst* p = (Inst*)c->plugin_data;
    uint32_t total = pr->frames_count, pos = 0, ne = pr->in_events ? pr->in_events->size(pr->in_events) : 0, ei = 0;
    float* o0 = 0; float* o1 = 0;
    if (pr->audio_outputs_count && pr->audio_outputs[0].data32) {
        o0 = pr->audio_outputs[0].data32[0];
        o1 = pr->audio_outputs[0].channel_count > 1 ? pr->audio_outputs[0].data32[1] : 0;
    }
    for (;;) {
        uint32_t n = total - pos > SXG_MAXFRAMES ? SXG_MAXFRAMES : total - pos;
        if (p->dead) {
            if (o0) memset(o0 + pos, 0, n * sizeof(float));
            if (o1) memset(o1 + pos, 0, n * sizeof(float));
        } else {
            p->sh->n_events = 0; p->sh->sysex_bytes = 0; p->sh->frames = (int32_t)n;
            while (ei < ne) {
                const clap_event_header_t* h = pr->in_events->get(pr->in_events, ei);
                if (pos + n < total && h->time >= pos + n) break;             // belongs to a later piece
                put_event(p, h, h->time > pos ? h->time - pos : 0);
                ei++;
            }
            if (!run_block(p, 1000)) {     // helper ended or hangs: silence from now on
                p->dead = 1;
                if (o0) memset(o0 + pos, 0, n * sizeof(float));
                if (o1) memset(o1 + pos, 0, n * sizeof(float));
            } else {
                if (o0) memcpy(o0 + pos, p->sh->out[0], n * sizeof(float));
                if (o1) memcpy(o1 + pos, p->sh->out[1], n * sizeof(float));
            }
        }
        pos += n;
        if (pos >= total) break;
    }
    return CLAP_PROCESS_CONTINUE;
}

static uint32_t ap_count(const clap_plugin_t* c, bool is_input) { (void)c; return is_input ? 0 : 1; }
static bool ap_get(const clap_plugin_t* c, uint32_t i, bool is_input, clap_audio_port_info_t* info)
{
    (void)c;
    if (is_input || i) return false;
    memset(info, 0, sizeof *info);
    info->id = 0; snprintf(info->name, sizeof info->name, "Main");
    info->flags = CLAP_AUDIO_PORT_IS_MAIN; info->channel_count = 2; info->port_type = CLAP_PORT_STEREO;
    info->in_place_pair = CLAP_INVALID_ID;
    return true;
}
static const clap_plugin_audio_ports_t ext_audio = { ap_count, ap_get };

static uint32_t np_count(const clap_plugin_t* c, bool is_input) { (void)c; return is_input ? 1 : 0; }
static bool np_get(const clap_plugin_t* c, uint32_t i, bool is_input, clap_note_port_info_t* info)
{
    (void)c;
    if (!is_input || i) return false;
    info->id = 0; snprintf(info->name, sizeof info->name, "MIDI");
    info->supported_dialects = CLAP_NOTE_DIALECT_MIDI | CLAP_NOTE_DIALECT_CLAP;
    info->preferred_dialect = CLAP_NOTE_DIALECT_MIDI;
    return true;
}
static const clap_plugin_note_ports_t ext_notes = { np_count, np_get };

// state: 'SXGB', version, length, plugin chunk (what the plugin itself saves for a VST2 host)
static bool st_save(const clap_plugin_t* c, const clap_ostream_t* s)
{
    Inst* p = (Inst*)c->plugin_data;
    if (p->dead) return false;
    if (!command(p, SXG_CMD_GET_CHUNK, 0, 0, 15000)) return false;
    uint32_t hdr[3] = { SXG_MAGIC, 1, p->sh->result ? p->sh->blob_len : 0 };
    const uint8_t* src = p->sh->blob; uint32_t left = hdr[2];
    const char* h = (const char*)hdr; int hl = sizeof hdr;
    while (hl > 0) { int64_t w = s->write(s, h, hl); if (w <= 0) return false; h += w; hl -= (int)w; }
    while (left) { int64_t w = s->write(s, src, left); if (w <= 0) return false; src += w; left -= (uint32_t)w; }
    return true;
}
static bool st_load(const clap_plugin_t* c, const clap_istream_t* s)
{
    Inst* p = (Inst*)c->plugin_data;
    if (p->dead) return false;
    uint32_t hdr[3]; char* d = (char*)hdr; int need = sizeof hdr;
    while (need > 0) { int64_t r = s->read(s, d, need); if (r <= 0) return false; d += r; need -= (int)r; }
    if (hdr[0] != SXG_MAGIC || hdr[2] > SXG_BLOB_MAX) return false;
    if (!hdr[2]) return true;
    blob_lock(p);                                                   // the blob is part of the mailbox
    uint8_t* b = p->sh->blob; uint32_t left = hdr[2];
    while (left) { int64_t r = s->read(s, b, left); if (r <= 0) { blob_unlock(p); return false; } b += r; left -= (uint32_t)r; }
    p->sh->blob_len = hdr[2];
    blob_unlock(p);
    return command(p, SXG_CMD_SET_CHUNK, 0, 0, 30000);
}
static const clap_plugin_state_t ext_state = { st_save, st_load };

static const void* pl_ext(const clap_plugin_t* c, const char* id)
{
    (void)c;
    if (!strcmp(id, CLAP_EXT_AUDIO_PORTS)) return &ext_audio;
    if (!strcmp(id, CLAP_EXT_NOTE_PORTS)) return &ext_notes;
    if (!strcmp(id, CLAP_EXT_STATE)) return &ext_state;
    return plat_ext(id);
}
static void pl_on_main(const clap_plugin_t* c) { (void)c; }

// ----------------------------------------------------------------------------- factory and entry

static uint32_t fac_count(const clap_plugin_factory_t* f) { (void)f; return 1; }
static const clap_plugin_descriptor_t* fac_desc(const clap_plugin_factory_t* f, uint32_t i) { (void)f; return i == 0 ? &g_desc : 0; }
static const clap_plugin_t* fac_create(const clap_plugin_factory_t* f, const clap_host_t* host, const char* id)
{
    (void)f;
    if (!id || strcmp(id, g_desc.id)) return 0;
    Inst* p = (Inst*)calloc(1, sizeof *p);
    if (!p) return 0;
    p->host = host; INST_INIT(p);
    p->plugin.desc = &g_desc; p->plugin.plugin_data = p;
    p->plugin.init = pl_init; p->plugin.destroy = pl_destroy; p->plugin.activate = pl_activate;
    p->plugin.deactivate = pl_deactivate; p->plugin.start_processing = pl_start; p->plugin.stop_processing = pl_stop;
    p->plugin.reset = pl_reset; p->plugin.process = pl_process; p->plugin.get_extension = pl_ext;
    p->plugin.on_main_thread = pl_on_main;
    return &p->plugin;
}
static const clap_plugin_factory_t g_factory = { fac_count, fac_desc, fac_create };


static bool entry_init(const char* path)
{
    if (!plat_entry_path(path)) return false;
    const char* name = g_stem8;
    for (int i = 0; NAMES[i].stem; i++) if (!strcmp(NAMES[i].stem, g_stem8)) name = NAMES[i].name;
    snprintf(g_id, sizeof g_id, "io.github.nightfright2k19.sxg-create-nf.%s", g_stem8);
    snprintf(g_name, sizeof g_name, "%s", name);
    memset(&g_desc, 0, sizeof g_desc);
    g_desc.clap_version = CLAP_VERSION;
    g_desc.id = g_id; g_desc.name = g_name; g_desc.vendor = "SXG-Create-NF";
    g_desc.url = "https://github.com/NightFright2k19/SXG-Create-NF";
    g_desc.manual_url = g_desc.url; g_desc.support_url = g_desc.url;
    g_desc.version = "1.0"; g_desc.description = "Yamaha MU sound via the 32-bit S-YXG plugin (CLAP bridge)";
    g_desc.features = g_features;
    return true;
}
static void entry_deinit(void) {}
static const void* entry_factory(const char* id) { return !strcmp(id, CLAP_PLUGIN_FACTORY_ID) ? &g_factory : 0; }
