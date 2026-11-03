// host32.c - 32-bit helper of the SXG-Create-NF CLAP bridge (issue #97).
// Loads one VST2 plugin DLL (32-bit), takes MIDI / commands from the 64-bit CLAP through shared memory and
// returns the audio. The window message loop and the commands run on the main thread, the audio on a second one.
//   sxgbridge32.exe <plugin.dll> <object prefix>                      Windows CLAP: named events and a named file mapping
//   sxgbridge32.exe <plugin.dll> net:<port>:<token>:<shared file>     Linux CLAP (run by Wine): the file is mapped from
//       the Linux side, the signals travel over two loopback TCP connections (control, audio) instead of events
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
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
static int      net;                    // 1: signals over sockets (Linux bridge)
static SOCKET   s_ctl = INVALID_SOCKET, s_aud = INVALID_SOCKET;
static char     title[64];
static int      floating;               // the editor window is a floating window of its own (macOS)

static void send_byte(SOCKET s, char c) { send(s, &c, 1, 0); }
static void sig_ready(void) { if (net) send_byte(s_ctl, 'R'); else SetEvent(h_ready); }
static void sig_adone(void) { if (net) send_byte(s_aud, 'a'); else SetEvent(h_adone); }
static void sig_cdone(void) { if (net) send_byte(s_ctl, 'c'); else SetEvent(h_cdone); }
static void wait_ago(void)
{
    if (!net) { WaitForSingleObject(h_ago, INFINITE); return; }
    char b;
    if (recv(s_aud, &b, 1, 0) <= 0) InterlockedExchange(&quitting, 1);       // the Linux side is gone
}
static DWORD WINAPI ctl_reader(LPVOID p)                 // socket mode: 'C' from the bridge = run a command
{
    (void)p; char b;
    while (recv(s_ctl, &b, 1, 0) > 0) if (b == 'C') SetEvent(h_cgo);
    InterlockedExchange(&quitting, 1); SetEvent(h_cgo);
    return 0;
}

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

// Rendering at the plugin's own rate. md[i] = frame (in this call) at which event i is sent, -1 = not in this call.
static void render(int frames, const int32_t* md, float* o0, float* o1)
{
    static char evbuf[sizeof(VstEventsHdr) + (SXG_MAXEVENTS) * sizeof(void*)];
    static VstMidiEvent mev[SXG_MAXEVENTS];
    static VstMidiSysexEvent sev[SXG_MAXEVENTS];
    static float in0[SXG_MAXFRAMES];       // silent inputs (an instrument has none, but be safe)
    static float spare[6][SXG_MAXFRAMES];
    uint32_t n = sh->n_events > SXG_MAXEVENTS ? SXG_MAXEVENTS : sh->n_events;
    for (int lo = 0; lo < frames; lo += SXG_MAXFRAMES) {
        int chunk = frames - lo > SXG_MAXFRAMES ? SXG_MAXFRAMES : frames - lo;
        int last = lo + chunk >= frames;
        VstEventsHdr* hdr = (VstEventsHdr*)evbuf;
        void** list = hdr->events;
        uint32_t cnt = 0;
        for (uint32_t i = 0; i < n; i++) {
            if (md[i] < 0 || md[i] < lo || (md[i] >= lo + chunk && !(last && md[i] >= frames))) continue;
            int32_t d = md[i] - lo; if (d > chunk - 1) d = chunk - 1;
            SxgEvent* e = &sh->events[i];
            if (e->kind == SXG_EV_SYSEX && (uint64_t)e->sysex_off + e->sysex_len <= SXG_SYSEX_MAX) {
                memset(&sev[i], 0, sizeof sev[i]);
                sev[i].type = 6; sev[i].byteSize = sizeof(VstMidiSysexEvent); sev[i].deltaFrames = d;
                sev[i].dumpBytes = (int32_t)e->sysex_len; sev[i].sysexDump = (char*)sh->sysex + e->sysex_off;
                list[cnt++] = &sev[i];
            } else {
                memset(&mev[i], 0, sizeof mev[i]);
                mev[i].type = 1; mev[i].byteSize = sizeof(VstMidiEvent); mev[i].deltaFrames = d;
                memcpy(mev[i].midiData, e->data, 3);
                list[cnt++] = &mev[i];
            }
        }
        if (cnt) { hdr->numEvents = (int32_t)cnt; hdr->reserved = 0; fx->dispatcher(fx, effProcessEvents, 0, 0, hdr, 0); }

        float* outs[8] = {0}; float* ins[2] = { in0, in0 };
        int no = fx->numOutputs > 8 ? 8 : fx->numOutputs;
        for (int i = 0; i < no; i++) outs[i] = i == 0 ? o0 + lo : i == 1 ? o1 + lo : spare[i - 2];
        for (int i = 0; i < no && i < 2; i++) memset(outs[i], 0, sizeof(float) * chunk);
        if (fx->processReplacing) fx->processReplacing(fx, ins, outs, chunk);
        else if (fx->process) fx->process(fx, ins, outs, chunk);
        if (no == 1) memcpy(o1 + lo, o0 + lo, sizeof(float) * chunk);      // mono plugin on both channels
    }
}

// Host rate the plugin does not support (the plugin then renders at 44100 Hz): resample its output.
static double host_rate = 44100.0;     // rate the CLAP host asked for
static double step = 1.0;              // plugin samples per host sample; 1.0 = no resampling
#define PBN 16384
static float pb[2][PBN];               // plugin-rate samples; pb[x][0] is the history sample
static int pb_have = 1;
static double pb_pos = 1.0;

static void resample_reset(void) { memset(pb, 0, sizeof pb); pb_have = 1; pb_pos = 1.0; }

static float cubic(const float* p, double t)
{
    float a = p[-1], b = p[0], c = p[1], d = p[2], f = (float)t;
    return b + 0.5f * f * (c - a + f * (2*a - 5*b + 4*c - d + f * (3*(b - c) + d - a)));
}

static void process_block(void)
{
    static int32_t md[SXG_MAXEVENTS];
    int frames = sh->frames;
    if (frames < 0) frames = 0;
    if (frames > SXG_MAXFRAMES) frames = SXG_MAXFRAMES;
    if (!fx) { memset(sh->out, 0, sizeof sh->out); return; }
    uint32_t n = sh->n_events > SXG_MAXEVENTS ? SXG_MAXEVENTS : sh->n_events;

    if (step == 1.0) {
        for (uint32_t i = 0; i < n; i++) {
            uint32_t d = sh->events[i].delta;
            md[i] = d < (uint32_t)frames ? (int32_t)d : (frames ? frames - 1 : 0);
        }
        render(frames, md, sh->out[0], sh->out[1]);
        return;
    }

    int maxcnt = (int)(4096.0 / step); if (maxcnt < 1) maxcnt = 1;
    for (int s = 0; s < frames; s += maxcnt) {
        int cnt = frames - s > maxcnt ? maxcnt : frames - s;
        int need = (int)(pb_pos + (cnt - 1) * step) + 3;
        int m = need - pb_have, any = 0;
        for (uint32_t i = 0; i < n; i++) {
            int32_t d = (int32_t)sh->events[i].delta;
            if (d > frames - 1) d = frames - 1;
            if (d >= s && (d < s + cnt || (s + cnt >= frames))) { md[i] = (int32_t)((d - s) * step); any = 1; }
            else md[i] = -1;
        }
        if (m < 1 && any) m = 1;
        if (m > 0) {
            for (uint32_t i = 0; i < n; i++) if (md[i] >= m) md[i] = m - 1;
            render(m, md, pb[0] + pb_have, pb[1] + pb_have);
            pb_have += m;
        }
        for (int k = 0; k < cnt; k++) {
            double x = pb_pos + k * step;
            int ix = (int)x; double t = x - ix;
            sh->out[0][s + k] = cubic(pb[0] + ix, t);
            sh->out[1][s + k] = cubic(pb[1] + ix, t);
        }
        pb_pos += cnt * step;
        int shift = (int)pb_pos - 1;
        if (shift > pb_have) shift = pb_have;     // the step can skip past what was rendered
        if (shift > 0) {
            memmove(pb[0], pb[0] + shift, sizeof(float) * (pb_have - shift));
            memmove(pb[1], pb[1] + shift, sizeof(float) * (pb_have - shift));
            pb_have -= shift; pb_pos -= shift;
        }
    }
}

static DWORD WINAPI audio_thread(LPVOID p)
{
    (void)p;
    SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_TIME_CRITICAL);
    for (;;) {
        wait_ago();
        if (quitting) break;
        process_block();
        sig_adone();
    }
    return 0;
}

// ----------------------------------------------------------------------------- editor window

static LRESULT CALLBACK ed_proc(HWND w, UINT m, WPARAM wp, LPARAM lp)
{
    if (m == WM_TIMER && fx && editor_open) { fx->dispatcher(fx, effEditIdle, 0, 0, 0, 0); return 0; }
    if (m == WM_CLOSE && floating) { ShowWindow(w, SW_HIDE); sh->editor_closed = 1; return 0; }      // closing only hides it
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

static void edit_open(HWND parent, int top_level)       // top_level: 0 child of parent, 1 bare popup (Linux), 2 floating window with title bar (macOS)
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
    if (top_level == 2) {
        RECT r = { 0, 0, ed_w, ed_h };
        DWORD st = WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX | WS_CLIPCHILDREN;
        AdjustWindowRect(&r, st, FALSE);
        floating = 1;
        editor_wnd = CreateWindowExA(WS_EX_TOPMOST, "SXGBridgeEditor", sh->name[0] ? sh->name : "S-YXG", st,
                                     CW_USEDEFAULT, CW_USEDEFAULT, r.right - r.left, r.bottom - r.top, 0, 0, GetModuleHandleA(0), 0);
    } else if (top_level)      // Linux: a window of its own that the CLAP moves into the host's window (X11 reparenting)
        editor_wnd = CreateWindowExA(WS_EX_TOOLWINDOW, "SXGBridgeEditor", title, WS_POPUP | WS_CLIPCHILDREN | WS_CLIPSIBLINGS,
                                     0, 0, ed_w, ed_h, 0, 0, GetModuleHandleA(0), 0);
    else
        editor_wnd = CreateWindowExA(0, "SXGBridgeEditor", "", WS_CHILD | WS_CLIPCHILDREN | WS_CLIPSIBLINGS,
                                     0, 0, ed_w, ed_h, parent, 0, GetModuleHandleA(0), 0);
    if (!editor_wnd) return;
    fx->dispatcher(fx, effEditOpen, 0, 0, editor_wnd, 0);
    editor_open = TRUE;
    edit_rect();                                         // some plugins only know the size once open
    if (ed_w > 0 && !floating) SetWindowPos(editor_wnd, 0, 0, 0, ed_w, ed_h, SWP_NOZORDER | SWP_NOMOVE);
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
        host_rate = (float)sh->arg[0] > 0 ? (double)sh->arg[0] : 44100.0;
        {   // S-YXG50 plays correctly at these rates only; at any other it renders at about 44100 Hz
            static const int ok[] = { 11025, 22050, 44100, 48000, 96000 };
            int native = 0;
            for (unsigned i = 0; i < sizeof ok / sizeof ok[0]; i++) if ((int)(host_rate + 0.5) == ok[i]) native = 1;
            sample_rate = native ? (float)host_rate : 44100.0f;
            step = native ? 1.0 : 44100.0 / host_rate;
            resample_reset();
        }
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
        edit_open((HWND)(UINT_PTR)(uint32_t)sh->arg[0], 0);
        sh->result = editor_open; sh->arg[0] = ed_w; sh->arg[1] = ed_h;
        break;
    case SXG_CMD_EDIT_OPEN_FLOAT:
        if (editor_open && editor_wnd) { sh->editor_closed = 0; ShowWindow(editor_wnd, SW_SHOW); }     // opened before and hidden by the user
        else edit_open(0, 2);
        sh->result = editor_open; sh->arg[0] = ed_w; sh->arg[1] = ed_h;
        break;
    case SXG_CMD_EDIT_OPEN_TOP:
        edit_open(0, 1);
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
    sig_ready();
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
    char prefix[512];
    WideCharToMultiByte(CP_UTF8, 0, argvw[2], -1, prefix, sizeof prefix, 0, 0);

    if (!strncmp(prefix, "net:", 4)) {                                    // Linux bridge, see the top of the file
        net = 1;
        char* port = prefix + 4; char* token = strchr(port, ':'); if (!token) return 2; *token++ = 0;
        char* file = strchr(token, ':'); if (!file) return 2; *file++ = 0;
        snprintf(title, sizeof title, "SXGBridge %s", token);
        WSADATA wd; WSAStartup(MAKEWORD(2, 2), &wd);
        for (int k = 0; k < 2; k++) {
            SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
            struct sockaddr_in a; memset(&a, 0, sizeof a);
            a.sin_family = AF_INET; a.sin_port = htons((u_short)atoi(port)); a.sin_addr.s_addr = inet_addr("127.0.0.1");
            if (connect(s, (struct sockaddr*)&a, sizeof a) != 0) return 3;
            int one = 1; setsockopt(s, IPPROTO_TCP, TCP_NODELAY, (const char*)&one, sizeof one);
            char hello[32]; snprintf(hello, sizeof hello, "%s%c", token, k == 0 ? 'C' : 'A');
            send(s, hello, (int)strlen(hello), 0);
            if (k == 0) s_ctl = s; else s_aud = s;
        }
        char win[MAX_PATH + 8] = "Z:";                                    // the Linux file system is drive Z: under Wine
        strncat(win, file, MAX_PATH);
        for (char* q = win; *q; q++) if (*q == '/') *q = '\\';
        h_map = CreateFileA(win, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, 0, OPEN_EXISTING, 0, 0);
        if (h_map == INVALID_HANDLE_VALUE) return 3;
        HANDLE fm = CreateFileMappingA(h_map, 0, PAGE_READWRITE, 0, (DWORD)sizeof(Shared), 0);
        if (!fm) return 3;
        sh = (Shared*)MapViewOfFile(fm, FILE_MAP_ALL_ACCESS, 0, 0, 0);
        if (!sh) return 3;
        h_cgo = CreateEventA(0, FALSE, FALSE, 0);
        CreateThread(0, 0, ctl_reader, 0, 0, 0);
    } else {
        h_map = open_obj(prefix, SXG_OBJ_MAP, 1);
        h_ready = open_obj(prefix, SXG_OBJ_READY, 0);
        h_ago = open_obj(prefix, SXG_OBJ_AGO, 0);   h_adone = open_obj(prefix, SXG_OBJ_ADONE, 0);
        h_cgo = open_obj(prefix, SXG_OBJ_CGO, 0);   h_cdone = open_obj(prefix, SXG_OBJ_CDONE, 0);
        if (!h_map || !h_ready || !h_ago || !h_adone || !h_cgo || !h_cdone) return 3;
        sh = (Shared*)MapViewOfFile(h_map, FILE_MAP_ALL_ACCESS, 0, 0, 0);
        if (!sh) return 3;
    }

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
    sig_ready();

    while (!quitting) {
        DWORD r = MsgWaitForMultipleObjects(1, &h_cgo, FALSE, INFINITE, QS_ALLINPUT);
        if (r == WAIT_OBJECT_0) { if (!quitting) { run_command(); sig_cdone(); } }
        else {
            MSG m;
            while (PeekMessageA(&m, 0, 0, 0, PM_REMOVE)) { TranslateMessage(&m); DispatchMessageA(&m); }
        }
    }
    edit_close();
    InterlockedExchange(&quitting, 1);
    if (net) { shutdown(s_aud, SD_BOTH); closesocket(s_aud); } else SetEvent(h_ago);
    WaitForSingleObject(at, 2000);
    fx->dispatcher(fx, effClose, 0, 0, 0, 0);
    return 0;
}
