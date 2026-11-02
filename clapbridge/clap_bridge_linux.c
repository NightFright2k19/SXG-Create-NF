// clap_bridge_linux.c - Linux CLAP plugin that runs one of the 32-bit S-YXG VST2 plugins under Wine (issue #97).
// Like the Windows bridge, the same file is copied once per plugin and takes the plugin from its own name:
//   <folder>/syxg1000.clap  ->  <folder>/../VST2/syxg1000.dll  (or <folder>/syxg1000.dll)  run by  wine <folder>/sxgbridge32.exe
// The helper is the same 32-bit program as on Windows. Shared memory is a file in /dev/shm that Wine maps too; the signals
// (audio block, command, done) travel over two loopback TCP connections. The editor is a Wine window that is moved into
// the host's X11 window (XReparentWindow), as other Wine bridges do. Needs Wine (wine in PATH, or SXG_WINE=<wine binary>).
// The part shared with the Windows bridge is in clap_common.h.
#define _GNU_SOURCE
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <pthread.h>
#include <signal.h>
#include <spawn.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <xcb/xcb.h>
#include "clap/clap.h"
#include "protocol.h"

extern char** environ;

static char g_dir[PATH_MAX], g_stem_raw[256], g_stem8[128];
static int  g_counter;

typedef struct {
    clap_plugin_t plugin;
    const clap_host_t* host;
    Shared* sh;
    int dead, active, gui_made, gui_open, gui_w, gui_h;
    char error[256];
    pid_t pid;
    int fd_ctl, fd_aud, shm_fd;
    char shm_path[96], token[24];
    pthread_mutex_t cmd_lock;
    xcb_connection_t* xc;
    xcb_window_t xparent, xchild, xroot;
    int last_x, last_y;
    clap_id timer;
} Inst;
#define INST_INIT(p) pthread_mutex_init(&(p)->cmd_lock, 0)

// ----------------------------------------------------------------------------- helper process and signals

// wait for one byte on fd until timeout; the helper counts as gone when the connection is closed or it has ended
static int wait_byte(Inst* p, int fd, char want, int timeout_ms)
{
    struct pollfd pf = { fd, POLLIN, 0 };
    for (;;) {
        int slice = timeout_ms > 200 ? 200 : timeout_ms;
        int r = poll(&pf, 1, slice);
        if (r > 0) {
            char b;
            ssize_t n = read(fd, &b, 1);
            if (n == 1) { if (b == want) return 1; continue; }
            if (n < 0 && errno == EINTR) continue;
            return 0;                                   // closed
        }
        if (r < 0 && errno != EINTR) return 0;
        timeout_ms -= slice;
        if (timeout_ms <= 0) return 0;
        if (waitpid(p->pid, 0, WNOHANG) == p->pid) { p->pid = 0; return 0; }
    }
}
static void send_byte(int fd, char c) { ssize_t n = write(fd, &c, 1); (void)n; }

static int command(Inst* p, int cmd, int a0, int a1, unsigned timeout)
{
    if (p->dead) return 0;
    pthread_mutex_lock(&p->cmd_lock);
    p->sh->cmd = cmd; p->sh->arg[0] = a0; p->sh->arg[1] = a1; p->sh->result = 0;
    send_byte(p->fd_ctl, 'C');
    int ok = wait_byte(p, p->fd_ctl, 'c', (int)timeout);
    if (!ok && (p->pid == 0 || kill(p->pid, 0) != 0)) p->dead = 1;
    pthread_mutex_unlock(&p->cmd_lock);
    return ok;
}
static int run_block(Inst* p, unsigned timeout)
{
    send_byte(p->fd_aud, 'A');
    struct pollfd pf = { p->fd_aud, POLLIN, 0 };
    int r = poll(&pf, 1, (int)timeout);
    char b;
    return r > 0 && read(p->fd_aud, &b, 1) == 1 && b == 'a';
}
static void blob_lock(Inst* p) { pthread_mutex_lock(&p->cmd_lock); }
static void blob_unlock(Inst* p) { pthread_mutex_unlock(&p->cmd_lock); }

static int exists(const char* f) { struct stat st; return stat(f, &st) == 0 && S_ISREG(st.st_mode); }

static int find_dll(char* out, size_t n)
{
    static const char* pat[] = { "%s/../VST2/%s.dll", "%s/%s.dll", "%s/../%s.dll", 0 };
    for (int i = 0; pat[i]; i++) {
        char t[PATH_MAX];
        snprintf(t, sizeof t, pat[i], g_dir, g_stem_raw);
        if (exists(t) && realpath(t, out)) { (void)n; return 1; }
    }
    return 0;
}

static int plat_start(Inst* p)
{
    char dll[PATH_MAX], exe[PATH_MAX], t[PATH_MAX + 16];
    p->fd_ctl = p->fd_aud = p->shm_fd = -1;
    if (!find_dll(dll, sizeof dll)) { snprintf(p->error, sizeof p->error, "%s.dll not found next to the CLAP (Plugins/VST2)", g_stem_raw); return 0; }
    snprintf(t, sizeof t, "%s/sxgbridge32.exe", g_dir);
    if (!exists(t) || !realpath(t, exe)) { snprintf(p->error, sizeof p->error, "sxgbridge32.exe not found next to the CLAP"); return 0; }

    int n = __sync_add_and_fetch(&g_counter, 1);
    snprintf(p->shm_path, sizeof p->shm_path, "/dev/shm/sxgb_%d_%d", (int)getpid(), n);
    p->shm_fd = open(p->shm_path, O_RDWR | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    if (p->shm_fd < 0 || ftruncate(p->shm_fd, sizeof(Shared)) != 0) { snprintf(p->error, sizeof p->error, "cannot create %s", p->shm_path); return 0; }
    p->sh = (Shared*)mmap(0, sizeof(Shared), PROT_READ | PROT_WRITE, MAP_SHARED, p->shm_fd, 0);
    if (p->sh == MAP_FAILED) { p->sh = 0; snprintf(p->error, sizeof p->error, "cannot map shared memory"); return 0; }
    memset(p->sh, 0, 4096);
    p->sh->magic = SXG_MAGIC; p->sh->version = SXG_VERSION;

    unsigned char rnd[8] = {0};
    int ur = open("/dev/urandom", O_RDONLY | O_CLOEXEC);
    if (ur >= 0) { ssize_t k = read(ur, rnd, sizeof rnd); (void)k; close(ur); }
    for (int i = 0; i < 8; i++) snprintf(p->token + 2 * i, 3, "%02x", rnd[i]);

    int ls = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
    struct sockaddr_in a; memset(&a, 0, sizeof a);
    a.sin_family = AF_INET; a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    socklen_t al = sizeof a;
    if (ls < 0 || bind(ls, (struct sockaddr*)&a, sizeof a) != 0 || listen(ls, 2) != 0 || getsockname(ls, (struct sockaddr*)&a, &al) != 0) {
        snprintf(p->error, sizeof p->error, "cannot open a local socket"); if (ls >= 0) close(ls); return 0;
    }

    // wine <helper> Z:\path\plugin.dll net:<port>:<token>:<shared file>
    char wdll[PATH_MAX + 4] = "Z:", arg2[PATH_MAX], wexe[PATH_MAX + 4] = "Z:";
    strncat(wdll, dll, PATH_MAX); for (char* q = wdll; *q; q++) if (*q == '/') *q = '\\';
    snprintf(arg2, sizeof arg2, "net:%d:%s:%s", ntohs(a.sin_port), p->token, p->shm_path);
    (void)wexe;
    const char* wine = getenv("SXG_WINE"); if (!wine || !*wine) wine = "wine";
    char* argv[] = { (char*)wine, exe, wdll, arg2, 0 };
    char** env = environ; int ne = 0; while (env[ne]) ne++;
    char** envp = (char**)calloc((size_t)ne + 3, sizeof *envp);
    int has_dbg = 0;
    for (int i = 0; i < ne; i++) { envp[i] = env[i]; if (!strncmp(env[i], "WINEDEBUG=", 10)) has_dbg = 1; }
    int k = ne; if (!has_dbg) envp[k++] = (char*)"WINEDEBUG=-all";
    posix_spawn_file_actions_t fa; posix_spawn_file_actions_init(&fa);
    if (!getenv("SXG_DEBUG")) {
        posix_spawn_file_actions_addopen(&fa, 0, "/dev/null", O_RDONLY, 0);
        posix_spawn_file_actions_addopen(&fa, 1, "/dev/null", O_WRONLY, 0);
        posix_spawn_file_actions_addopen(&fa, 2, "/dev/null", O_WRONLY, 0);
    }
    int sr = posix_spawnp(&p->pid, wine, &fa, 0, argv, envp);
    posix_spawn_file_actions_destroy(&fa); free(envp);
    if (sr != 0) { p->pid = 0; close(ls); snprintf(p->error, sizeof p->error, "cannot start Wine (%s): %s", wine, strerror(sr)); return 0; }

    // the helper connects twice: control, then audio
    for (int i = 0; i < 2; i++) {
        struct pollfd pf = { ls, POLLIN, 0 };
        int waited = 0, got = -1;
        while (waited < 120000) {
            int r = poll(&pf, 1, 200);
            if (r > 0) { got = accept4(ls, 0, 0, SOCK_CLOEXEC); break; }
            waited += 200;
            if (waitpid(p->pid, 0, WNOHANG) == p->pid) { p->pid = 0; break; }
        }
        if (got < 0) { close(ls); snprintf(p->error, sizeof p->error, p->pid ? "Wine did not start the helper in time" : "Wine ended without starting the helper (is Wine installed?)"); return 0; }
        char hello[24] = {0}; struct pollfd hp = { got, POLLIN, 0 };
        if (poll(&hp, 1, 5000) <= 0 || read(got, hello, 17) != 17 || strncmp(hello, p->token, 16) != 0 || (hello[16] != (i ? 'A' : 'C'))) { close(got); close(ls); snprintf(p->error, sizeof p->error, "unexpected connection"); return 0; }
        int one = 1; setsockopt(got, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
        if (i == 0) p->fd_ctl = got; else p->fd_aud = got;
    }
    close(ls);
    if (!wait_byte(p, p->fd_ctl, 'R', 120000)) { snprintf(p->error, sizeof p->error, "the helper ended while loading the plugin"); return 0; }
    unlink(p->shm_path); p->shm_path[0] = 0;                       // both sides have it open
    if (!p->sh->ok) { snprintf(p->error, sizeof p->error, "%s", p->sh->error[0] ? p->sh->error : "the plugin could not be loaded"); return 0; }
    return 1;
}

static void plat_stop(Inst* p)
{
    if (p->pid > 0) {
        if (!p->dead && p->sh && p->sh->ok && p->fd_ctl >= 0) command(p, SXG_CMD_QUIT, 0, 0, 3000);
        if (p->fd_ctl >= 0) { close(p->fd_ctl); p->fd_ctl = -1; }
        if (p->fd_aud >= 0) { close(p->fd_aud); p->fd_aud = -1; }
        for (int i = 0; i < 30 && p->pid > 0; i++) {
            if (waitpid(p->pid, 0, WNOHANG) == p->pid) { p->pid = 0; break; }
            usleep(100000);
        }
        if (p->pid > 0) { kill(p->pid, SIGKILL); waitpid(p->pid, 0, 0); p->pid = 0; }
    }
    if (p->fd_ctl >= 0) close(p->fd_ctl);
    if (p->fd_aud >= 0) close(p->fd_aud);
    p->fd_ctl = p->fd_aud = -1;
    if (p->sh) munmap(p->sh, sizeof(Shared));
    p->sh = 0;
    if (p->shm_fd >= 0) close(p->shm_fd);
    p->shm_fd = -1;
    if (p->shm_path[0]) unlink(p->shm_path);
}

// ----------------------------------------------------------------------------- editor (X11)

static xcb_atom_t atom(xcb_connection_t* c, const char* name)
{
    xcb_intern_atom_reply_t* r = xcb_intern_atom_reply(c, xcb_intern_atom(c, 0, (uint16_t)strlen(name), name), 0);
    xcb_atom_t a = r ? r->atom : XCB_ATOM_NONE; free(r); return a;
}
static int has_title(xcb_connection_t* c, xcb_window_t w, xcb_atom_t prop, xcb_atom_t type, const char* title)
{
    xcb_get_property_reply_t* r = xcb_get_property_reply(c, xcb_get_property(c, 0, w, prop, type, 0, 64), 0);
    int hit = 0;
    if (r) { int n = xcb_get_property_value_length(r); const char* v = (const char*)xcb_get_property_value(r);
             for (int i = 0; i + (int)strlen(title) <= n; i++) if (!strncmp(v + i, title, strlen(title))) hit = 1; }
    free(r); return hit;
}
static xcb_window_t find_window(xcb_connection_t* c, xcb_window_t w, const char* title, xcb_atom_t net_name, xcb_atom_t utf8, int depth)
{
    if (has_title(c, w, XCB_ATOM_WM_NAME, XCB_ATOM_ANY, title) || has_title(c, w, net_name, utf8, title)) return w;
    if (depth <= 0) return 0;
    xcb_query_tree_reply_t* t = xcb_query_tree_reply(c, xcb_query_tree(c, w), 0);
    xcb_window_t found = 0;
    if (t) { xcb_window_t* ch = xcb_query_tree_children(t);
             for (int i = 0; i < xcb_query_tree_children_length(t) && !found; i++) found = find_window(c, ch[i], title, net_name, utf8, depth - 1);
             free(t); }
    return found;
}

// tell Wine where its window is on the screen (it does not see the host's window moving)
static void send_position(Inst* p)
{
    if (!p->xc || !p->xchild) return;
    xcb_translate_coordinates_reply_t* r = xcb_translate_coordinates_reply(p->xc, xcb_translate_coordinates(p->xc, p->xchild, p->xroot, 0, 0), 0);
    if (!r) return;
    int x = r->dst_x, y = r->dst_y; free(r);
    if (x == p->last_x && y == p->last_y) return;
    p->last_x = x; p->last_y = y;
    xcb_configure_notify_event_t ev; memset(&ev, 0, sizeof ev);
    ev.response_type = XCB_CONFIGURE_NOTIFY; ev.event = p->xchild; ev.window = p->xchild;
    ev.x = (int16_t)x; ev.y = (int16_t)y; ev.width = (uint16_t)p->gui_w; ev.height = (uint16_t)p->gui_h;
    xcb_send_event(p->xc, 0, p->xchild, XCB_EVENT_MASK_STRUCTURE_NOTIFY, (const char*)&ev);
    xcb_flush(p->xc);
}

static void x_release(Inst* p)
{
    const clap_host_timer_support_t* ts = p->timer != CLAP_INVALID_ID && p->host->get_extension ?
        (const clap_host_timer_support_t*)p->host->get_extension(p->host, CLAP_EXT_TIMER_SUPPORT) : 0;
    if (ts && ts->unregister_timer) ts->unregister_timer(p->host, p->timer);
    p->timer = CLAP_INVALID_ID;
    if (p->xc) { xcb_disconnect(p->xc); p->xc = 0; }
    p->xchild = 0;
}
static void plat_gui_close(Inst* p)
{
    if (p->gui_open) command(p, SXG_CMD_EDIT_CLOSE, 0, 0, 5000);
    p->gui_open = 0; x_release(p);
}

static bool gui_supported(const clap_plugin_t* c, const char* api, bool floating)
{
    Inst* p = (Inst*)c->plugin_data;
    return !floating && api && !strcmp(api, CLAP_WINDOW_API_X11) && !p->dead && p->sh && p->sh->has_editor;
}
static bool gui_preferred(const clap_plugin_t* c, const char** api, bool* floating)
{
    if (!gui_supported(c, CLAP_WINDOW_API_X11, false)) return false;
    *api = CLAP_WINDOW_API_X11; *floating = false; return true;
}
static bool gui_create(const clap_plugin_t* c, const char* api, bool floating)
{
    Inst* p = (Inst*)c->plugin_data;
    if (!gui_supported(c, api, floating)) return false;
    if (command(p, SXG_CMD_EDIT_RECT, 0, 0, 10000)) { p->gui_w = p->sh->arg[0]; p->gui_h = p->sh->arg[1]; }
    if (p->gui_w <= 0) { p->gui_w = 640; p->gui_h = 480; }
    p->gui_made = 1; p->timer = CLAP_INVALID_ID; return true;
}
static void gui_destroy(const clap_plugin_t* c) { Inst* p = (Inst*)c->plugin_data; plat_gui_close(p); p->gui_made = 0; }
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
    if (!p->gui_made || !win || !win->x11) return false;
    if (!command(p, SXG_CMD_EDIT_OPEN_TOP, 0, 0, 30000) || !p->sh->result) return false;
    p->gui_w = p->sh->arg[0]; p->gui_h = p->sh->arg[1]; p->gui_open = 1;
    p->xc = xcb_connect(0, 0);
    if (!p->xc || xcb_connection_has_error(p->xc)) return false;
    p->xparent = (xcb_window_t)win->x11;
    p->xroot = xcb_setup_roots_iterator(xcb_get_setup(p->xc)).data->root;
    xcb_atom_t net_name = atom(p->xc, "_NET_WM_NAME"), utf8 = atom(p->xc, "UTF8_STRING");
    char title[64]; snprintf(title, sizeof title, "SXGBridge %s", p->token);
    for (int i = 0; i < 100 && !p->xchild; i++) {                  // the window appears a moment after the command
        p->xchild = find_window(p->xc, p->xroot, title, net_name, utf8, 3);
        if (!p->xchild) usleep(50000);
    }
    if (!p->xchild) return false;
    xcb_reparent_window(p->xc, p->xchild, p->xparent, 0, 0);
    xcb_map_window(p->xc, p->xchild);
    xcb_flush(p->xc);
    p->last_x = p->last_y = -100000;
    send_position(p);
    const clap_host_timer_support_t* ts = p->host->get_extension ? (const clap_host_timer_support_t*)p->host->get_extension(p->host, CLAP_EXT_TIMER_SUPPORT) : 0;
    if (ts && ts->register_timer) ts->register_timer(p->host, 100, &p->timer);
    return true;
}
static bool gui_transient(const clap_plugin_t* c, const clap_window_t* w) { (void)c; (void)w; return false; }
static void gui_title(const clap_plugin_t* c, const char* t) { (void)c; (void)t; }
static bool gui_show(const clap_plugin_t* c)
{
    Inst* p = (Inst*)c->plugin_data;
    if (!p->gui_open) return false;
    command(p, SXG_CMD_EDIT_SHOW, 1, 0, 5000);
    if (p->xc) { xcb_map_window(p->xc, p->xchild); xcb_flush(p->xc); send_position(p); }
    return true;
}
static bool gui_hide(const clap_plugin_t* c)
{
    Inst* p = (Inst*)c->plugin_data;
    if (!p->gui_open) return false;
    if (p->xc) { xcb_unmap_window(p->xc, p->xchild); xcb_flush(p->xc); }
    command(p, SXG_CMD_EDIT_SHOW, 0, 0, 5000);
    return true;
}
static const clap_plugin_gui_t ext_gui = {
    gui_supported, gui_preferred, gui_create, gui_destroy, gui_scale, gui_size, gui_can_resize, gui_hints,
    gui_adjust, gui_set_size, gui_set_parent, gui_transient, gui_title, gui_show, gui_hide
};
static void on_timer(const clap_plugin_t* c, clap_id id)
{
    Inst* p = (Inst*)c->plugin_data;
    if (id == p->timer && p->gui_open) send_position(p);
}
static const clap_plugin_timer_support_t ext_timer = { on_timer };

static const void* plat_ext(const char* id)
{
    if (!strcmp(id, CLAP_EXT_GUI)) return &ext_gui;
    if (!strcmp(id, CLAP_EXT_TIMER_SUPPORT)) return &ext_timer;
    return 0;
}

static int plat_entry_path(const char* path)
{
    char full[PATH_MAX];
    snprintf(full, sizeof full, "%s", path);
    char* slash = strrchr(full, '/');
    const char* base = slash ? slash + 1 : full;
    if (slash) { *slash = 0; snprintf(g_dir, sizeof g_dir, "%s", full[0] ? full : "/"); } else snprintf(g_dir, sizeof g_dir, ".");
    snprintf(g_stem_raw, sizeof g_stem_raw, "%s", base);
    char* dot = strrchr(g_stem_raw, '.'); if (dot) *dot = 0;
    snprintf(g_stem8, sizeof g_stem8, "%s", g_stem_raw);
    for (char* q = g_stem8; *q; q++) if (*q >= 'A' && *q <= 'Z') *q += 32;
    return 1;
}

#include "clap_common.h"

__attribute__((visibility("default"))) const clap_plugin_entry_t clap_entry = { CLAP_VERSION_INIT, entry_init, entry_deinit, entry_factory };
