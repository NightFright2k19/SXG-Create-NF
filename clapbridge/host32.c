// host32.c - 32-bit helper of the SXG-Create-NF CLAP bridge (issue #97).
// Loads one VST2 plugin DLL (32-bit), takes MIDI / commands from the 64-bit CLAP through shared memory and
// returns the audio. The window message loop and the commands run on the main thread, the audio on a second one.
//   sxgbridge32.exe <plugin.dll> <object prefix>
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "vst2.h"
#include "protocol.h"

static Shared*  sh;
static HANDLE   h_ready, h_ago, h_adone, h_cgo, h_cdone, h_map;
static AEffect* fx;
static HMODULE  dll;
static volatile LONG quitting;
static float    sample_rate = 44100.0f;
static VstTimeInfo time_info;
static HWND     editor_wnd;
static BOOL     editor_open;
static int      ed_w, ed_h;

// ----------------------------------------------------------------------------- host callback of the plugin

static intptr_t __cdecl master(AEffect* e, int32_t op, int32_t idx, intptr_t val, void* ptr, float opt)
{
    (void)e; (void)idx; (void)opt;
    switch (op) {
    case audioMasterVersion:           return 2400;
    case audioMasterCurrentId:         return 0;
    case audioMasterGetSampleRate:     return (intptr_t)sample_rate;
    case audioMasterGetBlockSize:      return SXG_MAXFRAMES;
    case audioMasterGetCurrentProcessLevel: return 0;
    case audioMasterGetLanguage:       return 1;
    case audioMasterGetVendorVersion:  return 1000;
    case audioMasterGetVendorString:   if (ptr) strcpy((char*)ptr, "SXG-Create-NF"); return 1;
    case audioMasterGetProductString:  if (ptr) strcpy((char*)ptr, "CLAP bridge"); return 1;
    case audioMasterGetTime:
        memset(&time_info, 0, sizeof time_info);
        time_info.sampleRate = sample_rate; time_info.tempo = 120.0;
        time_info.timeSigNumerator = 4; time_info.timeSigDenominator = 4;
        return (intptr_t)&time_info;
    case audioMasterCanDo: {
        const char* s = (const char*)ptr;
        return s && (!strcmp(s, "sendVstEvents") || !strcmp(s, "sendVstMidiEvent") || !strcmp(s, "receiveVstTimeInfo")
                     || !strcmp(s, "sizeWindow")) ? 1 : 0;
    }
    case audioMasterSizeWindow:        // the panel of these plugins has a fixed size; remember it for the window
        if (idx > 0 && (int32_t)val > 0) { ed_w = idx; ed_h = (int32_t)val; }
        return 1;
    default: return 0;                 // automate, idle, wantMidi, ioChanged, updateDisplay ...
    }
}

// ----------------------------------------------------------------------------- audio thread

static void process_block(void)
{
    static char evbuf[sizeof(VstEventsHdr) + (SXG_MAXEVENTS) * sizeof(void*)];
    static VstMidiEvent mev[SXG_MAXEVENTS];
    static VstMidiSysexEvent sev[SXG_MAXEVENTS];
    static float in0[SXG_MAXFRAMES];       // silent inputs (an instrument has none, but be safe)
    int frames = sh->frames;
    if (frames < 0) frames = 0;
    if (frames > SXG_MAXFRAMES) frames = SXG_MAXFRAMES;
    if (!fx) { memset(sh->out, 0, sizeof sh->out); return; }

    VstEventsHdr* hdr = (VstEventsHdr*)evbuf;
    void** list = hdr->events;
    uint32_t n = sh->n_events > SXG_MAXEVENTS ? SXG_MAXEVENTS : sh->n_events;
    for (uint32_t i = 0; i < n; i++) {
        SxgEvent* e = &sh->events[i];
        int32_t d = e->delta < (uint32_t)frames ? (int32_t)e->delta : (frames ? frames - 1 : 0);
        if (e->kind == SXG_EV_SYSEX && (uint64_t)e->sysex_off + e->sysex_len <= SXG_SYSEX_MAX) {
            memset(&sev[i], 0, sizeof sev[i]);
            sev[i].type = 6; sev[i].byteSize = sizeof(VstMidiSysexEvent); sev[i].deltaFrames = d;
            sev[i].dumpBytes = (int32_t)e->sysex_len; sev[i].sysexDump = (char*)sh->sysex + e->sysex_off;
            list[i] = &sev[i];
        } else {
            memset(&mev[i], 0, sizeof mev[i]);
            mev[i].type = 1; mev[i].byteSize = sizeof(VstMidiEvent); mev[i].deltaFrames = d;
            memcpy(mev[i].midiData, e->data, 3);
            list[i] = &mev[i];
        }
    }
    if (n) { hdr->numEvents = (int32_t)n; hdr->reserved = 0; fx->dispatcher(fx, effProcessEvents, 0, 0, hdr, 0); }

    float* outs[8] = {0}; float* ins[2] = { in0, in0 };
    static float spare[6][SXG_MAXFRAMES];
    int no = fx->numOutputs > 8 ? 8 : fx->numOutputs;
    for (int i = 0; i < no; i++) outs[i] = i < SXG_OUTS ? sh->out[i] : spare[i - SXG_OUTS];
    memset(sh->out, 0, sizeof sh->out);
    if (fx->processReplacing) fx->processReplacing(fx, ins, outs, frames);
    else if (fx->process) fx->process(fx, ins, outs, frames);
    if (no == 1) memcpy(sh->out[1], sh->out[0], sizeof(float) * frames);      // mono plugin on both channels
}

static DWORD WINAPI audio_thread(LPVOID p)
{
    (void)p;
    SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_TIME_CRITICAL);
    for (;;) {
        WaitForSingleObject(h_ago, INFINITE);
        if (quitting) break;
        process_block();
        SetEvent(h_adone);
    }
    return 0;
}

// ----------------------------------------------------------------------------- editor window

static LRESULT CALLBACK ed_proc(HWND w, UINT m, WPARAM wp, LPARAM lp)
{
    if (m == WM_TIMER && fx && editor_open) { fx->dispatcher(fx, effEditIdle, 0, 0, 0, 0); return 0; }
    return DefWindowProcA(w, m, wp, lp);
}

static void edit_rect(void)
{
    ERect* r = 0;
    ed_w = ed_h = 0;
    if (fx && (fx->flags & effFlagsHasEditor)) {
        fx->dispatcher(fx, effEditGetRect, 0, 0, &r, 0);
        if (r) { ed_w = r->right - r->left; ed_h = r->bottom - r->top; }
    }
}

static void edit_open(HWND parent)
{
    static int registered;
    if (editor_open || !fx || !(fx->flags & effFlagsHasEditor)) return;
    if (!registered) {
        WNDCLASSA wc = {0};
        wc.lpfnWndProc = ed_proc; wc.hInstance = GetModuleHandleA(0); wc.lpszClassName = "SXGBridgeEditor";
        wc.hCursor = LoadCursorA(0, IDC_ARROW);
        RegisterClassA(&wc); registered = 1;
    }
    edit_rect();
    if (ed_w <= 0) { ed_w = 640; ed_h = 480; }
    editor_wnd = CreateWindowExA(0, "SXGBridgeEditor", "", WS_CHILD | WS_CLIPCHILDREN | WS_CLIPSIBLINGS,
                                 0, 0, ed_w, ed_h, parent, 0, GetModuleHandleA(0), 0);
    if (!editor_wnd) return;
    fx->dispatcher(fx, effEditOpen, 0, 0, editor_wnd, 0);
    editor_open = TRUE;
    edit_rect();                                         // some plugins only know the size once open
    if (ed_w > 0) SetWindowPos(editor_wnd, 0, 0, 0, ed_w, ed_h, SWP_NOZORDER | SWP_NOMOVE);
    SetTimer(editor_wnd, 1, 33, 0);
    ShowWindow(editor_wnd, SW_SHOW);
}

static void edit_close(void)
{
    if (!editor_open) return;
    KillTimer(editor_wnd, 1);
    fx->dispatcher(fx, effEditClose, 0, 0, 0, 0);
    editor_open = FALSE;
    DestroyWindow(editor_wnd); editor_wnd = 0;
}

// ----------------------------------------------------------------------------- commands (main thread)

static void run_command(void)
{
    sh->result = 0;
    switch (sh->cmd) {
    case SXG_CMD_ACTIVATE:
        sample_rate = (float)sh->arg[0] > 0 ? (float)sh->arg[0] : 44100.0f;
        fx->dispatcher(fx, effSetSampleRate, 0, 0, 0, sample_rate);
        fx->dispatcher(fx, effSetBlockSize, 0, SXG_MAXFRAMES, 0, 0);
        fx->dispatcher(fx, effMainsChanged, 0, 1, 0, 0);
        fx->dispatcher(fx, effStartProcess, 0, 0, 0, 0);
        break;
    case SXG_CMD_DEACTIVATE:
        fx->dispatcher(fx, effStopProcess, 0, 0, 0, 0);
        fx->dispatcher(fx, effMainsChanged, 0, 0, 0, 0);
        break;
    case SXG_CMD_EDIT_RECT:  edit_rect(); sh->arg[0] = ed_w; sh->arg[1] = ed_h; break;
    case SXG_CMD_EDIT_OPEN:
        edit_open((HWND)(UINT_PTR)(uint32_t)sh->arg[0]);
        sh->result = editor_open; sh->arg[0] = ed_w; sh->arg[1] = ed_h;
        break;
    case SXG_CMD_EDIT_CLOSE: edit_close(); break;
    case SXG_CMD_EDIT_SHOW:  if (editor_wnd) ShowWindow(editor_wnd, sh->arg[0] ? SW_SHOW : SW_HIDE); break;
    case SXG_CMD_GET_CHUNK: {
        void* p = 0;
        intptr_t n = (fx->flags & effFlagsProgramChunks) ? fx->dispatcher(fx, effGetChunk, 0, 0, &p, 0) : 0;
        if (n > 0 && p && n <= SXG_BLOB_MAX) { memcpy(sh->blob, p, (size_t)n); sh->blob_len = (uint32_t)n; sh->result = 1; }
        else sh->blob_len = 0;
        break;
    }
    case SXG_CMD_SET_CHUNK:
        if (fx->flags & effFlagsProgramChunks) {
            fx->dispatcher(fx, effSetChunk, 0, (intptr_t)sh->blob_len, sh->blob, 0);
            sh->result = 1;
        }
        break;
    case SXG_CMD_QUIT: InterlockedExchange(&quitting, 1); break;
    }
}

// ----------------------------------------------------------------------------- start

static void fail(const char* msg)
{
    snprintf(sh->error, sizeof sh->error, "%s", msg);
    sh->ok = 0;
    SetEvent(h_ready);
}

typedef AEffect* (__cdecl *VstMain)(AudioMasterCallback);

static HANDLE open_obj(const char* prefix, const char* suffix, int kind)
{
    char name[128];
    snprintf(name, sizeof name, "%s%s", prefix, suffix);
    if (kind == 0) return OpenEventA(EVENT_MODIFY_STATE | SYNCHRONIZE, FALSE, name);
    return OpenFileMappingA(FILE_MAP_ALL_ACCESS, FALSE, name);
}

int WINAPI WinMain(HINSTANCE hi, HINSTANCE hp, LPSTR cmd, int show)
{
    (void)hi; (void)hp; (void)cmd; (void)show;
    int argc; LPWSTR* argvw = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (!argvw || argc < 3) return 2;
    char prefix[96];
    WideCharToMultiByte(CP_ACP, 0, argvw[2], -1, prefix, sizeof prefix, 0, 0);

    h_map = open_obj(prefix, SXG_OBJ_MAP, 1);
    h_ready = open_obj(prefix, SXG_OBJ_READY, 0);
    h_ago = open_obj(prefix, SXG_OBJ_AGO, 0);   h_adone = open_obj(prefix, SXG_OBJ_ADONE, 0);
    h_cgo = open_obj(prefix, SXG_OBJ_CGO, 0);   h_cdone = open_obj(prefix, SXG_OBJ_CDONE, 0);
    if (!h_map || !h_ready || !h_ago || !h_adone || !h_cgo || !h_cdone) return 3;
    sh = (Shared*)MapViewOfFile(h_map, FILE_MAP_ALL_ACCESS, 0, 0, 0);
    if (!sh) return 3;

    // the plugin finds its ini file and resources next to itself
    dll = LoadLibraryExW(argvw[1], 0, LOAD_WITH_ALTERED_SEARCH_PATH);
    if (!dll) { char m[200]; snprintf(m, sizeof m, "LoadLibrary failed (error %lu)", GetLastError()); fail(m); return 4; }
    VstMain entry = (VstMain)(void*)GetProcAddress(dll, "VSTPluginMain");
    if (!entry) entry = (VstMain)(void*)GetProcAddress(dll, "main");
    if (!entry) { fail("no VSTPluginMain in the plugin"); return 4; }
    fx = entry(master);
    if (!fx || fx->magic != kEffectMagic) {
        char m[120]; snprintf(m, sizeof m, "not a VST2 plugin (entry returned %p, magic %08x)", (void*)fx, fx ? (unsigned)fx->magic : 0u);
        fail(m); return 4;
    }
    fx->dispatcher(fx, effOpen, 0, 0, 0, 0);
    sh->outputs = fx->numOutputs; sh->inputs = fx->numInputs; sh->flags = fx->flags;
    sh->unique_id = fx->uniqueID; sh->has_editor = (fx->flags & effFlagsHasEditor) ? 1 : 0;
    fx->dispatcher(fx, effGetEffectName, 0, 0, sh->name, 0);
    sh->name[sizeof sh->name - 1] = 0;
    sh->ok = 1;

    HANDLE at = CreateThread(0, 0, audio_thread, 0, 0, 0);
    SetEvent(h_ready);

    while (!quitting) {
        DWORD r = MsgWaitForMultipleObjects(1, &h_cgo, FALSE, INFINITE, QS_ALLINPUT);
        if (r == WAIT_OBJECT_0) { run_command(); SetEvent(h_cdone); }
        else {
            MSG m;
            while (PeekMessageA(&m, 0, 0, 0, PM_REMOVE)) { TranslateMessage(&m); DispatchMessageA(&m); }
        }
    }
    edit_close();
    InterlockedExchange(&quitting, 1); SetEvent(h_ago);
    WaitForSingleObject(at, 2000);
    fx->dispatcher(fx, effClose, 0, 0, 0, 0);
    return 0;
}
