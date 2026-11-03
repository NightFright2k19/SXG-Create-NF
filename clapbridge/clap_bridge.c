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

#define SXG_KIND "CLAP"

static wchar_t g_dir[MAX_PATH], g_stem[MAX_PATH];
static char    g_stem8[128];

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

#include "win_transport.h"

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
