// clap_bridge.c - 64-bit CLAP plugin that runs one of the 32-bit S-YXG VST2 plugins in a helper process (issue #97).
// The same file is copied once per plugin; it takes the plugin from its own name:
//   <folder>\syxg1000.clap  ->  <folder>\..\VST2\syxg1000.dll  (or <folder>\syxg1000.dll)  run by  <folder>\sxgbridge32.exe
// Audio, MIDI and the editor window go through shared memory and four events (protocol.h).
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <wchar.h>
#include "clap/clap.h"
#include "protocol.h"

#define HELPER_NAME L"sxgbridge32.exe"

static wchar_t g_dir[MAX_PATH], g_stem[MAX_PATH];
static char    g_id[200], g_name[128], g_stem8[128];
static clap_plugin_descriptor_t g_desc;
static const char* g_features[] = { CLAP_PLUGIN_FEATURE_INSTRUMENT, CLAP_PLUGIN_FEATURE_SYNTHESIZER, CLAP_PLUGIN_FEATURE_STEREO, 0 };
static volatile LONG g_counter;

static const struct { const char* stem; const char* name; } NAMES[] = {
    { "syxg15", "S-YXG MU15" }, { "syxgmu15", "S-YXG MU15" }, { "syxgmu50", "S-YXG MU50" }, { "syxg50", "S-YXG50" },
    { "syxg80", "S-YXG MU80" }, { "syxg90", "S-YXG MU90" }, { "syxg100", "S-YXG MU100" }, { "syxg128", "S-YXG MU128" },
    { "syxg1000", "S-YXG MU1000" }, { "syxg2000", "S-YXG MU2000" }, { "syxg2006le", "S-YXG2006LE" }, { 0, 0 }
};

// ----------------------------------------------------------------------------- instance

typedef struct {
    clap_plugin_t plugin;
    const clap_host_t* host;
    HANDLE proc, job, map, ready, ago, adone, cgo, cdone;
    Shared* sh;
    int dead, active, gui_made, gui_open, gui_w, gui_h;
    SRWLOCK cmd_lock;
    char error[256];
} Inst;

static void log_error(Inst* p, const char* m)
{
    if (p->host && p->host->get_extension) {
        const clap_host_log_t* l = (const clap_host_log_t*)p->host->get_extension(p->host, CLAP_EXT_LOG);
        if (l && l->log) l->log(p->host, CLAP_LOG_ERROR, m);
    }
}

// one command to the helper; blocks until it is done (the editor commands run on the helper's UI thread).
// Editor commands create or destroy a window whose parent belongs to this process: Windows then sends messages
// to the host's window thread, so while it waits it has to answer them ('pump', MsgWait + PeekMessage).
static int command_ex(Inst* p, int cmd, int a0, int a1, DWORD timeout, int pump)
{
    if (p->dead) return 0;
    AcquireSRWLockExclusive(&p->cmd_lock);
    p->sh->cmd = cmd; p->sh->arg[0] = a0; p->sh->arg[1] = a1; p->sh->result = 0;
    SetEvent(p->cgo);
    HANDLE w[2] = { p->cdone, p->proc };
    DWORD r, t0 = GetTickCount();
    for (;;) {
        DWORD left = timeout - (GetTickCount() - t0);
        if (timeout != INFINITE && (int)left <= 0) { r = WAIT_TIMEOUT; break; }
        r = pump ? MsgWaitForMultipleObjects(2, w, FALSE, left, QS_SENDMESSAGE) : WaitForMultipleObjects(2, w, FALSE, left);
        if (r == WAIT_OBJECT_0 + 2) { MSG m; PeekMessageA(&m, 0, 0, 0, PM_NOREMOVE); continue; }   // dispatches the sent messages
        break;
    }
    int ok = (r == WAIT_OBJECT_0);
    if (r == WAIT_OBJECT_0 + 1) p->dead = 1;
    ReleaseSRWLockExclusive(&p->cmd_lock);
    return ok;
}
static int command(Inst* p, int cmd, int a0, int a1, DWORD timeout) { return command_ex(p, cmd, a0, a1, timeout, 0); }

static int file_exists(const wchar_t* f) { DWORD a = GetFileAttributesW(f); return a != INVALID_FILE_ATTRIBUTES && !(a & FILE_ATTRIBUTE_DIRECTORY); }

static int find_dll(wchar_t* out, size_t n)
{
    static const wchar_t* pat[] = { L"%ls\\..\\VST2\\%ls.dll", L"%ls\\%ls.dll", L"%ls\\..\\%ls.dll", 0 };
    for (int i = 0; pat[i]; i++) {
        _snwprintf(out, n, pat[i], g_dir, g_stem);
        wchar_t full[MAX_PATH];
        if (GetFullPathNameW(out, MAX_PATH, full, 0) && file_exists(full)) { wcsncpy(out, full, n); return 1; }
    }
    return 0;
}

static int start_helper(Inst* p)
{
    wchar_t dllp[MAX_PATH], exe[MAX_PATH], cmd[3 * MAX_PATH], pfx[64];
    char pfx8[64];
    if (!find_dll(dllp, MAX_PATH)) { snprintf(p->error, sizeof p->error, "%ls.dll not found next to the CLAP (Plugins\\VST2)", g_stem); return 0; }
    _snwprintf(exe, MAX_PATH, L"%ls\\%ls", g_dir, HELPER_NAME);
    if (!file_exists(exe)) { snprintf(p->error, sizeof p->error, "sxgbridge32.exe not found next to the CLAP"); return 0; }

    snprintf(pfx8, sizeof pfx8, "Local\\SXGB%lu_%ld_", GetCurrentProcessId(), InterlockedIncrement(&g_counter));
    MultiByteToWideChar(CP_ACP, 0, pfx8, -1, pfx, 64);
    char nm[128];
    #define OBJ(sfx) (snprintf(nm, sizeof nm, "%s%s", pfx8, sfx), nm)
    p->map = CreateFileMappingA(INVALID_HANDLE_VALUE, 0, PAGE_READWRITE, 0, (DWORD)sizeof(Shared), OBJ(SXG_OBJ_MAP));
    p->ready = CreateEventA(0, FALSE, FALSE, OBJ(SXG_OBJ_READY));
    p->ago = CreateEventA(0, FALSE, FALSE, OBJ(SXG_OBJ_AGO));   p->adone = CreateEventA(0, FALSE, FALSE, OBJ(SXG_OBJ_ADONE));
    p->cgo = CreateEventA(0, FALSE, FALSE, OBJ(SXG_OBJ_CGO));   p->cdone = CreateEventA(0, FALSE, FALSE, OBJ(SXG_OBJ_CDONE));
    if (!p->map || !p->ready || !p->ago || !p->adone || !p->cgo || !p->cdone) { snprintf(p->error, sizeof p->error, "cannot create shared objects"); return 0; }
    p->sh = (Shared*)MapViewOfFile(p->map, FILE_MAP_ALL_ACCESS, 0, 0, 0);
    if (!p->sh) { snprintf(p->error, sizeof p->error, "cannot map shared memory"); return 0; }
    memset(p->sh, 0, 4096);
    p->sh->magic = SXG_MAGIC; p->sh->version = SXG_VERSION;

    _snwprintf(cmd, 3 * MAX_PATH, L"\"%ls\" \"%ls\" %ls", exe, dllp, pfx);
    p->job = CreateJobObjectA(0, 0);                      // the helper ends with the host, even if the host crashes
    if (p->job) {
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION li; memset(&li, 0, sizeof li);
        li.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        SetInformationJobObject(p->job, JobObjectExtendedLimitInformation, &li, sizeof li);
    }
    STARTUPINFOW si; PROCESS_INFORMATION pi; memset(&si, 0, sizeof si); si.cb = sizeof si;
    if (!CreateProcessW(exe, cmd, 0, 0, FALSE, CREATE_NO_WINDOW | CREATE_BREAKAWAY_FROM_JOB | CREATE_SUSPENDED, 0, g_dir, &si, &pi)) {
        // a host whose own job forbids breakaway: start again without that flag
        if (!CreateProcessW(exe, cmd, 0, 0, FALSE, CREATE_NO_WINDOW | CREATE_SUSPENDED, 0, g_dir, &si, &pi)) {
            snprintf(p->error, sizeof p->error, "cannot start sxgbridge32.exe (error %lu)", GetLastError()); return 0;
        }
    }
    if (p->job) AssignProcessToJobObject(p->job, pi.hProcess);
    ResumeThread(pi.hThread); CloseHandle(pi.hThread);
    p->proc = pi.hProcess;

    HANDLE w[2] = { p->ready, p->proc };
    DWORD r = WaitForMultipleObjects(2, w, FALSE, 120000);        // large tables: loading can take a while
    if (r != WAIT_OBJECT_0) { snprintf(p->error, sizeof p->error, r == WAIT_OBJECT_0 + 1 ? "the 32-bit helper ended while loading the plugin" : "the plugin took too long to load"); return 0; }
    if (!p->sh->ok) { snprintf(p->error, sizeof p->error, "%s", p->sh->error[0] ? p->sh->error : "the plugin could not be loaded"); return 0; }
    return 1;
}

static void stop_helper(Inst* p)
{
    if (p->proc && !p->dead && p->sh && p->sh->ok) {
        command(p, SXG_CMD_QUIT, 0, 0, 3000);
        if (WaitForSingleObject(p->proc, 3000) != WAIT_OBJECT_0) TerminateProcess(p->proc, 0);
    } else if (p->proc) TerminateProcess(p->proc, 0);
    if (p->sh) UnmapViewOfFile(p->sh);
    HANDLE* h[] = { &p->proc, &p->job, &p->map, &p->ready, &p->ago, &p->adone, &p->cgo, &p->cdone };
    for (size_t i = 0; i < sizeof h / sizeof *h; i++) if (*h[i]) { CloseHandle(*h[i]); *h[i] = 0; }
    p->sh = 0;
}

// ----------------------------------------------------------------------------- plugin

static bool pl_init(const clap_plugin_t* c)
{
    Inst* p = (Inst*)c->plugin_data;
    if (!start_helper(p)) { log_error(p, p->error); stop_helper(p); p->dead = 1; return false; }
    return true;
}
static void pl_destroy(const clap_plugin_t* c)
{
    Inst* p = (Inst*)c->plugin_data;
    if (p->gui_open) command_ex(p, SXG_CMD_EDIT_CLOSE, 0, 0, 5000, 1);
    stop_helper(p);
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
    SetEvent(p->ago);
    HANDLE w[2] = { p->adone, p->proc };
    if (WaitForMultipleObjects(2, w, FALSE, 2000) != WAIT_OBJECT_0) p->dead = 1;
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
            SetEvent(p->ago);
            HANDLE w[2] = { p->adone, p->proc };
            if (WaitForMultipleObjects(2, w, FALSE, 1000) != WAIT_OBJECT_0) {     // helper ended or hangs: silence from now on
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

// ----------------------------------------------------------------------------- extensions

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
    AcquireSRWLockExclusive(&p->cmd_lock);                          // the blob is part of the mailbox
    uint8_t* b = p->sh->blob; uint32_t left = hdr[2];
    while (left) { int64_t r = s->read(s, b, left); if (r <= 0) { ReleaseSRWLockExclusive(&p->cmd_lock); return false; } b += r; left -= (uint32_t)r; }
    p->sh->blob_len = hdr[2];
    ReleaseSRWLockExclusive(&p->cmd_lock);
    return command(p, SXG_CMD_SET_CHUNK, 0, 0, 30000);
}
static const clap_plugin_state_t ext_state = { st_save, st_load };

static bool gui_supported(const clap_plugin_t* c, const char* api, bool floating)
{
    Inst* p = (Inst*)c->plugin_data;
    return !floating && api && !strcmp(api, CLAP_WINDOW_API_WIN32) && !p->dead && p->sh && p->sh->has_editor;
}
static bool gui_preferred(const clap_plugin_t* c, const char** api, bool* floating)
{
    if (!gui_supported(c, CLAP_WINDOW_API_WIN32, false)) return false;
    *api = CLAP_WINDOW_API_WIN32; *floating = false; return true;
}
static bool gui_create(const clap_plugin_t* c, const char* api, bool floating)
{
    Inst* p = (Inst*)c->plugin_data;
    if (!gui_supported(c, api, floating)) return false;
    if (command(p, SXG_CMD_EDIT_RECT, 0, 0, 10000)) { p->gui_w = p->sh->arg[0]; p->gui_h = p->sh->arg[1]; }
    if (p->gui_w <= 0) { p->gui_w = 640; p->gui_h = 480; }
    p->gui_made = 1; return true;
}
static void gui_destroy(const clap_plugin_t* c)
{
    Inst* p = (Inst*)c->plugin_data;
    if (p->gui_open) command_ex(p, SXG_CMD_EDIT_CLOSE, 0, 0, 5000, 1);
    p->gui_open = 0; p->gui_made = 0;
}
static bool gui_scale(const clap_plugin_t* c, double s) { (void)c; (void)s; return false; }
static bool gui_size(const clap_plugin_t* c, uint32_t* w, uint32_t* h)
{
    Inst* p = (Inst*)c->plugin_data;
    if (!p->gui_made) return false;
    *w = (uint32_t)p->gui_w; *h = (uint32_t)p->gui_h; return true;
}
static bool gui_can_resize(const clap_plugin_t* c) { (void)c; return false; }
static bool gui_hints(const clap_plugin_t* c, clap_gui_resize_hints_t* h) { (void)c; (void)h; return false; }
static bool gui_adjust(const clap_plugin_t* c, uint32_t* w, uint32_t* h) { return gui_size(c, w, h); }
static bool gui_set_size(const clap_plugin_t* c, uint32_t w, uint32_t h) { Inst* p = (Inst*)c->plugin_data; return (int)w == p->gui_w && (int)h == p->gui_h; }
static bool gui_set_parent(const clap_plugin_t* c, const clap_window_t* win)
{
    Inst* p = (Inst*)c->plugin_data;
    if (!p->gui_made || !win || !win->win32) return false;
    uint32_t h32 = (uint32_t)(uintptr_t)win->win32;                // window handles are 32 bits wide on Windows
    if (!command_ex(p, SXG_CMD_EDIT_OPEN, (int)h32, 0, 30000, 1) || !p->sh->result) return false;
    p->gui_w = p->sh->arg[0]; p->gui_h = p->sh->arg[1];
    p->gui_open = 1; return true;
}
static bool gui_transient(const clap_plugin_t* c, const clap_window_t* w) { (void)c; (void)w; return false; }
static void gui_title(const clap_plugin_t* c, const char* t) { (void)c; (void)t; }
static bool gui_show(const clap_plugin_t* c) { Inst* p = (Inst*)c->plugin_data; if (p->gui_open) command_ex(p, SXG_CMD_EDIT_SHOW, 1, 0, 5000, 1); return p->gui_open; }
static bool gui_hide(const clap_plugin_t* c) { Inst* p = (Inst*)c->plugin_data; if (p->gui_open) command_ex(p, SXG_CMD_EDIT_SHOW, 0, 0, 5000, 1); return p->gui_open; }
static const clap_plugin_gui_t ext_gui = {
    gui_supported, gui_preferred, gui_create, gui_destroy, gui_scale, gui_size, gui_can_resize, gui_hints,
    gui_adjust, gui_set_size, gui_set_parent, gui_transient, gui_title, gui_show, gui_hide
};

static const void* pl_ext(const clap_plugin_t* c, const char* id)
{
    (void)c;
    if (!strcmp(id, CLAP_EXT_AUDIO_PORTS)) return &ext_audio;
    if (!strcmp(id, CLAP_EXT_NOTE_PORTS)) return &ext_notes;
    if (!strcmp(id, CLAP_EXT_STATE)) return &ext_state;
    if (!strcmp(id, CLAP_EXT_GUI)) return &ext_gui;
    return 0;
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
    p->host = host; InitializeSRWLock(&p->cmd_lock);
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
    wchar_t full[MAX_PATH];
    if (!MultiByteToWideChar(CP_UTF8, 0, path, -1, full, MAX_PATH)) return false;
    wchar_t* slash = wcsrchr(full, L'\\'); if (!slash) slash = wcsrchr(full, L'/');
    wchar_t* base = slash ? slash + 1 : full;
    if (slash) { *slash = 0; wcsncpy(g_dir, full, MAX_PATH - 1); } else wcscpy(g_dir, L".");
    wcsncpy(g_stem, base, MAX_PATH - 1);
    wchar_t* dot = wcsrchr(g_stem, L'.'); if (dot) *dot = 0;
    WideCharToMultiByte(CP_UTF8, 0, g_stem, -1, g_stem8, sizeof g_stem8, 0, 0);
    for (char* q = g_stem8; *q; q++) if (*q >= 'A' && *q <= 'Z') *q += 32;
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

__declspec(dllexport) const clap_plugin_entry_t clap_entry = { CLAP_VERSION_INIT, entry_init, entry_deinit, entry_factory };
