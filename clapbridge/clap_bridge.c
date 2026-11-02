// clap_bridge.c - 64-bit CLAP plugin that runs one of the 32-bit S-YXG VST2 plugins in a helper process (issue #97).
// The same file is copied once per plugin; it takes the plugin from its own name:
//   <folder>\syxg1000.clap  ->  <folder>\..\VST2\syxg1000.dll  (or <folder>\syxg1000.dll)  run by  <folder>\sxgbridge32.exe
// Audio, MIDI and the editor window go through shared memory and four events (protocol.h). The part shared with the
// Linux bridge is in clap_common.h.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wchar.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "clap/clap.h"
#include "protocol.h"

#define HELPER_NAME L"sxgbridge32.exe"

static wchar_t g_dir[MAX_PATH], g_stem[MAX_PATH];
static char    g_stem8[128];
static volatile LONG g_counter;

typedef struct {
    clap_plugin_t plugin;
    const clap_host_t* host;
    Shared* sh;
    int dead, active, gui_made, gui_open, gui_w, gui_h;
    char error[256];
    HANDLE proc, job, map, ready, ago, adone, cgo, cdone;
    SRWLOCK cmd_lock;
} Inst;
#define INST_INIT(p) InitializeSRWLock(&(p)->cmd_lock)

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

static int plat_start(Inst* p)
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

static void plat_stop(Inst* p)
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

static int run_block(Inst* p, unsigned timeout)
{
    SetEvent(p->ago);
    HANDLE w[2] = { p->adone, p->proc };
    return WaitForMultipleObjects(2, w, FALSE, timeout) == WAIT_OBJECT_0;
}
static void blob_lock(Inst* p) { AcquireSRWLockExclusive(&p->cmd_lock); }
static void blob_unlock(Inst* p) { ReleaseSRWLockExclusive(&p->cmd_lock); }
static void plat_gui_close(Inst* p) { if (p->gui_open) command_ex(p, SXG_CMD_EDIT_CLOSE, 0, 0, 5000, 1); }

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

static const void* plat_ext(const char* id)
{
    return !strcmp(id, CLAP_EXT_GUI) ? &ext_gui : 0;
}

static int plat_entry_path(const char* path)
{
    wchar_t full[MAX_PATH];
    if (!MultiByteToWideChar(CP_UTF8, 0, path, -1, full, MAX_PATH)) return 0;
    // hosts mix both separators (e.g. Woof!: <folder>\plugins/name.clap): the last of either one ends the folder
    wchar_t* slash = wcsrchr(full, L'\\'); wchar_t* slash2 = wcsrchr(full, L'/');
    if (!slash || (slash2 && slash2 > slash)) slash = slash2;
    wchar_t* base = slash ? slash + 1 : full;
    if (slash) { *slash = 0; wcsncpy(g_dir, full, MAX_PATH - 1); } else wcscpy(g_dir, L".");
    wcsncpy(g_stem, base, MAX_PATH - 1);
    wchar_t* dot = wcsrchr(g_stem, L'.'); if (dot) *dot = 0;
    WideCharToMultiByte(CP_UTF8, 0, g_stem, -1, g_stem8, sizeof g_stem8, 0, 0);
    for (char* q = g_stem8; *q; q++) if (*q >= 'A' && *q <= 'Z') *q += 32;
    return 1;
}

#include "clap_common.h"

__declspec(dllexport) const clap_plugin_entry_t clap_entry = { CLAP_VERSION_INIT, entry_init, entry_deinit, entry_factory };
