// vst2_bridge.c - 64-bit VST2 plugin that runs one of the 32-bit S-YXG VST2 plugins in a helper process (issue #104).
// The same file is copied once per plugin under the name <plugin>_x64.dll; it takes the plugin from its own name:
//   <folder>\syxg1000_x64.dll  ->  <folder>\..\syxg1000.dll  (or <folder>\syxg1000.dll)  run by  <folder>\sxgbridge32.exe
// (the patcher writes Plugins\VST2\x64\syxg1000_x64.dll next to Plugins\VST2\syxg1000.dll). Audio, MIDI and the editor window
// go through shared memory and four events (protocol.h), the same link as the CLAP bridge (win_transport.h).
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wchar.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "vst2.h"
#include "protocol.h"

#define SXG_KIND "plugin"

static wchar_t g_dir[MAX_PATH], g_stem[MAX_PATH];
static char    g_stem8[128];

enum { effFlagsCanReplacing = 16 };
enum {
    effSetProgram = 2, effGetProgram = 3, effGetProgramName = 5, effGetPlugCategory = 35,
    effGetVendorString = 47, effGetProductString = 48, effGetVendorVersion = 49, effCanDo = 51, effGetVstVersion = 58
};

typedef struct {
    AEffect fx;                         // first member: the host's AEffect* is also the Inst*
    AudioMasterCallback master;
    Shared* sh;
    int dead, active, gui_made, gui_open, gui_w, gui_h;
    char error[256];
    HANDLE proc, job, map, ready, ago, adone, cgo, cdone;
    SRWLOCK cmd_lock;
    float rate; int block;
    ERect rect;
    uint8_t* chunk; size_t chunk_cap;
    // events given by effProcessEvents wait here until the next process call (they may reach beyond SXG_MAXFRAMES)
    uint32_t n_ev, sysex_n; SxgEvent ev[SXG_MAXEVENTS]; uint8_t sysex[SXG_SYSEX_MAX];
} Inst;

static int file_exists(const wchar_t* f);
static int find_dll(wchar_t* out, size_t n);
#include "win_transport.h"

static int find_dll(wchar_t* out, size_t n)
{
    static const wchar_t* pat[] = { L"%ls\\..\\%ls.dll", L"%ls\\%ls.dll", L"%ls\\..\\..\\%ls.dll", 0 };
    for (int i = 0; pat[i]; i++) {
        _snwprintf(out, n, pat[i], g_dir, g_stem);
        wchar_t full[MAX_PATH];
        if (GetFullPathNameW(out, MAX_PATH, full, 0) && file_exists(full)) { wcsncpy(out, full, n); return 1; }
    }
    return 0;
}

static void log_to_file(const char* m)
{
    const char* t = getenv("TEMP"); if (!t || !*t) t = "C:\\Windows\\Temp";
    char f[1024]; snprintf(f, sizeof f, "%s\\sxgbridge.log", t);
    FILE* fp = fopen(f, "a");
    if (fp) { fprintf(fp, "%s_x64: %s\n", g_stem8, m); fclose(fp); }
}

// ----------------------------------------------------------------------------- events and audio

static void queue_midi(Inst* p, uint32_t delta, const uint8_t* d)
{
    if (p->n_ev >= SXG_MAXEVENTS) return;
    SxgEvent* e = &p->ev[p->n_ev++]; memset(e, 0, sizeof *e);
    e->delta = delta; e->kind = SXG_EV_MIDI; memcpy(e->data, d, 3);
}
static void queue_sysex(Inst* p, uint32_t delta, const uint8_t* d, uint32_t n)
{
    if (p->n_ev >= SXG_MAXEVENTS || n > SXG_SYSEX_MAX || p->sysex_n + n > SXG_SYSEX_MAX) return;
    SxgEvent* e = &p->ev[p->n_ev++]; memset(e, 0, sizeof *e);
    e->delta = delta; e->kind = SXG_EV_SYSEX; e->sysex_off = p->sysex_n; e->sysex_len = n;
    memcpy(p->sysex + p->sysex_n, d, n); p->sysex_n += n;
}
static void take_events(Inst* p, const VstEventsHdr* h)
{
    for (int i = 0; i < h->numEvents; i++) {
        const int32_t* ty = (const int32_t*)h->events[i];
        if (!ty) continue;
        if (*ty == 1) {                                         // kVstMidiType
            const VstMidiEvent* m = (const VstMidiEvent*)ty;
            queue_midi(p, m->deltaFrames < 0 ? 0 : (uint32_t)m->deltaFrames, (const uint8_t*)m->midiData);
        } else if (*ty == 6) {                                  // kVstSysExType
            const VstMidiSysexEvent* s = (const VstMidiSysexEvent*)ty;
            if (s->sysexDump && s->dumpBytes > 0) queue_sysex(p, s->deltaFrames < 0 ? 0 : (uint32_t)s->deltaFrames, (const uint8_t*)s->sysexDump, (uint32_t)s->dumpBytes);
        }
    }
}

static int activate(Inst* p)
{
    if (p->dead) return 0;
    if (p->active) return 1;
    if (!command(p, SXG_CMD_ACTIVATE, (int)((p->rate > 0 ? p->rate : 44100.0f) + 0.5f), p->block, 30000)) return 0;
    p->active = 1; return 1;
}

static void process(Inst* p, float** out, int32_t frames, int add)
{
    uint32_t total = frames > 0 ? (uint32_t)frames : 0, pos = 0, ei = 0;
    int nch = p->fx.numOutputs > SXG_OUTS ? SXG_OUTS : p->fx.numOutputs;
    if (!p->active) activate(p);                                // hosts that never switch the plugin on
    while (pos < total) {
        uint32_t n = total - pos > SXG_MAXFRAMES ? SXG_MAXFRAMES : total - pos;
        int ok = !p->dead && p->active;
        if (ok) {
            Shared* s = p->sh;
            s->n_events = 0; s->sysex_bytes = 0; s->frames = (int32_t)n;
            while (ei < p->n_ev) {
                const SxgEvent* e = &p->ev[ei];
                if (pos + n < total && e->delta >= pos + n) break;      // belongs to a later piece
                SxgEvent* d = &s->events[s->n_events++];
                *d = *e; d->delta = e->delta > pos ? e->delta - pos : 0;
                if (e->kind == SXG_EV_SYSEX) { d->sysex_off = s->sysex_bytes; memcpy(s->sysex + s->sysex_bytes, p->sysex + e->sysex_off, e->sysex_len); s->sysex_bytes += e->sysex_len; }
                ei++;
            }
            if (!run_block(p, 1000)) { p->dead = 1; ok = 0; }       // helper ended or hangs: silence from now on
        }
        for (int c = 0; c < nch; c++) {
            if (!out[c]) continue;
            float* o = out[c] + pos;
            if (!ok) { if (!add) memset(o, 0, n * sizeof(float)); }
            else if (add) for (uint32_t i = 0; i < n; i++) o[i] += p->sh->out[c][i];
            else memcpy(o, p->sh->out[c], n * sizeof(float));
        }
        pos += n;
    }
    p->n_ev = 0; p->sysex_n = 0;
}

static void __cdecl vst_process(AEffect* fx, float** in, float** out, int32_t frames) { (void)in; process((Inst*)fx, out, frames, 1); }
static void __cdecl vst_process_replacing(AEffect* fx, float** in, float** out, int32_t frames) { (void)in; process((Inst*)fx, out, frames, 0); }
static void __cdecl vst_set_parameter(AEffect* fx, int32_t i, float v) { (void)fx; (void)i; (void)v; }
static float __cdecl vst_get_parameter(AEffect* fx, int32_t i) { (void)fx; (void)i; return 0; }

// ----------------------------------------------------------------------------- dispatcher

static void copy_str(void* dst, const char* s, size_t max) { snprintf((char*)dst, max, "%s", s); }

static intptr_t __cdecl vst_dispatch(AEffect* fx, int32_t op, int32_t index, intptr_t value, void* ptr, float opt)
{
    Inst* p = (Inst*)fx;
    (void)index;
    switch (op) {
    case effClose:
        if (p->gui_open) command_ex(p, SXG_CMD_EDIT_CLOSE, 0, 0, 5000, 1);
        plat_stop(p);
        free(p->chunk); free(p);
        return 0;
    case effSetSampleRate: p->rate = opt; return 0;
    case effSetBlockSize:  p->block = (int)value; return 0;
    case effMainsChanged:
        if (value) activate(p);
        else { if (p->active) command(p, SXG_CMD_DEACTIVATE, 0, 0, 10000); p->active = 0; }
        return 0;
    case effProcessEvents: if (ptr) take_events(p, (const VstEventsHdr*)ptr); return 1;
    case effEditGetRect: {
        if (p->dead || !p->sh || !p->sh->has_editor) return 0;
        if (!p->gui_w && command(p, SXG_CMD_EDIT_RECT, 0, 0, 10000)) { p->gui_w = p->sh->arg[0]; p->gui_h = p->sh->arg[1]; }
        if (p->gui_w <= 0) { p->gui_w = 640; p->gui_h = 480; }
        p->rect.top = 0; p->rect.left = 0; p->rect.bottom = (int16_t)p->gui_h; p->rect.right = (int16_t)p->gui_w;
        if (ptr) *(ERect**)ptr = &p->rect;
        return 1;
    }
    case effEditOpen: {
        if (p->dead || !p->sh || !p->sh->has_editor || !ptr) return 0;
        if (p->gui_open) return 1;
        uint32_t h32 = (uint32_t)(uintptr_t)ptr;                // window handles are 32 bits wide on Windows
        if (!command_ex(p, SXG_CMD_EDIT_OPEN, (int)h32, 0, 30000, 1) || !p->sh->result) return 0;
        p->gui_w = p->sh->arg[0]; p->gui_h = p->sh->arg[1];
        p->gui_open = 1; return 1;
    }
    case effEditClose:
        if (p->gui_open) command_ex(p, SXG_CMD_EDIT_CLOSE, 0, 0, 5000, 1);
        p->gui_open = 0; return 0;
    case effGetChunk: {
        if (p->dead || !(p->fx.flags & effFlagsProgramChunks) || !ptr) return 0;
        if (!command(p, SXG_CMD_GET_CHUNK, 0, 0, 15000) || !p->sh->result) return 0;
        blob_lock(p);
        size_t n = p->sh->blob_len;
        if (n > p->chunk_cap) { free(p->chunk); p->chunk = (uint8_t*)malloc(n); p->chunk_cap = p->chunk ? n : 0; }
        if (p->chunk) memcpy(p->chunk, p->sh->blob, n); else n = 0;
        blob_unlock(p);
        *(void**)ptr = p->chunk;
        return (intptr_t)n;
    }
    case effSetChunk: {
        if (p->dead || !ptr || value <= 0 || value > SXG_BLOB_MAX) return 0;
        blob_lock(p);
        memcpy(p->sh->blob, ptr, (size_t)value); p->sh->blob_len = (uint32_t)value;
        blob_unlock(p);
        return command(p, SXG_CMD_SET_CHUNK, 0, 0, 30000) ? 1 : 0;
    }
    case effGetProgram: return 0;
    case effGetProgramName: if (ptr) copy_str(ptr, "Default", 24); return 0;
    case effGetEffectName: case effGetProductString: if (ptr) copy_str(ptr, p->sh && p->sh->name[0] ? p->sh->name : "S-YXG", 32); return 1;
    case effGetVendorString: if (ptr) copy_str(ptr, "SXG-Create-NF", 64); return 1;
    case effGetVendorVersion: return 1000;
    case effGetVstVersion: return 2400;
    case effGetPlugCategory: return 2;                          // kPlugCategSynth
    case effCanDo:
        if (ptr && (!strcmp((char*)ptr, "receiveVstEvents") || !strcmp((char*)ptr, "receiveVstMidiEvent"))) return 1;
        return 0;
    default: return 0;
    }
}

// ----------------------------------------------------------------------------- entry

static void set_names(HMODULE self)
{
    wchar_t full[MAX_PATH];
    if (!GetModuleFileNameW(self, full, MAX_PATH)) wcscpy(full, L".\\x.dll");
    wchar_t* slash = wcsrchr(full, L'\\'); wchar_t* slash2 = wcsrchr(full, L'/');
    if (!slash || (slash2 && slash2 > slash)) slash = slash2;
    wchar_t* base = slash ? slash + 1 : full;
    if (slash) { *slash = 0; wcsncpy(g_dir, full, MAX_PATH - 1); } else wcscpy(g_dir, L".");
    wcsncpy(g_stem, base, MAX_PATH - 1);
    wchar_t* dot = wcsrchr(g_stem, L'.'); if (dot) *dot = 0;
    size_t n = wcslen(g_stem);                                  // syxg1000_x64 -> syxg1000
    if (n > 4 && !_wcsicmp(g_stem + n - 4, L"_x64")) g_stem[n - 4] = 0;
    WideCharToMultiByte(CP_UTF8, 0, g_stem, -1, g_stem8, sizeof g_stem8, 0, 0);
    for (char* q = g_stem8; *q; q++) if (*q >= 'A' && *q <= 'Z') *q += 32;
}

static HMODULE g_self;
BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID r) { (void)r; if (reason == DLL_PROCESS_ATTACH) g_self = (HMODULE)h; return TRUE; }

__declspec(dllexport) AEffect* VSTPluginMain(AudioMasterCallback master)
{
    if (!g_stem[0]) set_names(g_self);
    Inst* p = (Inst*)calloc(1, sizeof *p);
    if (!p) return 0;
    InitializeSRWLock(&p->cmd_lock);
    p->master = master; p->rate = 44100.0f; p->block = 1024;
    if (!plat_start(p)) { log_to_file(p->error); plat_stop(p); free(p); return 0; }
    AEffect* fx = &p->fx;
    fx->magic = kEffectMagic; fx->dispatcher = vst_dispatch; fx->process = vst_process;
    fx->setParameter = vst_set_parameter; fx->getParameter = vst_get_parameter; fx->processReplacing = vst_process_replacing;
    fx->numPrograms = 1; fx->numParams = 0; fx->numInputs = 0;
    fx->numOutputs = p->sh->outputs > 0 ? p->sh->outputs : 2;
    fx->flags = (p->sh->flags & (effFlagsHasEditor | effFlagsProgramChunks)) | effFlagsCanReplacing | effFlagsIsSynth;
    fx->uniqueID = p->sh->unique_id; fx->version = 1000;
    fx->object = p;
    return fx;
}
// older hosts look for "main"
__declspec(dllexport) AEffect* main_entry(AudioMasterCallback master) __asm__("main");
AEffect* main_entry(AudioMasterCallback master) { return VSTPluginMain(master); }
