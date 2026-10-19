/* S-YXG2006LE editor (issue #39): panel window (400 x 114) and Setup page for the patched SGP2.DLL.
 *
 * Freestanding C, compiled and linked by mksgp2.py into a flat blob that is appended to the code of section
 * .sxg (params.asm). The blob starts with a table of jumps (8 bytes each, see entries below); params.asm
 * calls them from the plugin's dispatcher (effEditGetRect / effEditOpen / effEditClose / effEditIdle) with
 * the C calling convention of the VST dispatcher (cdecl).
 *
 * The DLL imports only KERNEL32 / ADVAPI32, so every other API (user32, gdi32, comctl32) is looked up with
 * GetProcAddress, which the DLL does import (IAT at base + 0x5703C; GetModuleHandleA at base + 0x57040).
 * Parameters go through the plugin's own getParameter / setParameter (params.asm: getp / setp_h), so host
 * automation and the saved state stay as they are.
 *
 * Several instances of the plugin may live in one process (and several copies of the DLL): no state is kept
 * per process except the table of open editors (claimed per AEffect with an atomic compare-and-swap) and the
 * window class, whose name contains the load address of this DLL.
 */
typedef unsigned int u32; typedef int i32; typedef unsigned short u16; typedef unsigned char u8;
typedef void *PTR;
#define WINAPI __attribute__((stdcall))
#define NULL ((void *)0)

/* ---- VST ------------------------------------------------------------------------------------------------ */
typedef struct AEffect AEffect;
struct AEffect {
    i32 magic; PTR dispatcher, process;
    void (*setParameter)(AEffect *, i32, float);
    float (*getParameter)(AEffect *, i32);
    i32 numPrograms, numParams;
};
typedef struct { short top, left, bottom, right; } ERect;

/* ---- Win32 (just what is needed) ------------------------------------------------------------------------ */
typedef struct { i32 left, top, right, bottom; } RECT;
typedef struct { PTR hdc; i32 fErase; RECT rc; i32 fRestore, fInc; u8 res[32]; } PAINTSTRUCT;
typedef struct { u32 style; PTR proc; i32 cbCls, cbWnd; PTR inst, icon, cursor, brush; const char *menu, *cls; } WNDCLASSA;
typedef struct { PTR from; u32 id; i32 code; } NMHDR;
typedef struct { u32 mask, state, stateMask; char *text; i32 cch, image; i32 param; } TCITEMA;
typedef struct { u32 size, icc; } INITCC;

#define WS_POPUP 0x80000000u
#define WS_CHILD 0x40000000u
#define WS_VISIBLE 0x10000000u
#define WS_BORDER 0x00800000u
#define WS_TABSTOP 0x00010000u
#define WS_GROUP 0x00020000u
#define WS_CLIPSIBLINGS 0x04000000u
#define WS_EX_TOOLWINDOW 0x80u
#define BS_AUTOCHECKBOX 3
#define BS_GROUPBOX 7
#define BS_DEFPUSHBUTTON 1
#define SS_CENTER 1
#define SS_CENTERIMAGE 0x200
#define WM_CREATE 1
#define WM_DESTROY 2
#define WM_CLOSE 0x10
#define WM_PAINT 0xF
#define WM_ERASEBKGND 0x14
#define WM_SETFONT 0x30
#define WM_NOTIFY 0x4E
#define WM_COMMAND 0x111
#define WM_HSCROLL 0x114
#define WM_LBUTTONDOWN 0x201
#define WM_LBUTTONUP 0x202
#define WM_TIMER 0x113
#define WM_MOUSEWHEEL 0x20A
#define BM_GETCHECK 0xF0
#define BM_SETCHECK 0xF1
#define TBM_GETPOS 0x400
#define TBM_SETPOS 0x405
#define TBM_SETRANGE 0x406
#define TBM_SETTICFREQ 0x414
#define TBM_SETPAGESIZE 0x415
#define TCM_INSERTITEMA 0x1307
#define TCM_GETCURSEL 0x130B
#define TCN_SELCHANGE ((i32)-551)
#define HTCAPTION 2
#define HTCLIENT 1
#define SRCCOPY 0x00CC0020u
#define GWL_USERDATA (-21)

/* functions: filled by GetProcAddress, in this order (module: 0 user32, 1 gdi32, 2 comctl32) */
#define APIS \
    X(0, RegisterClassA) X(0, CreateWindowExA) X(0, DestroyWindow) X(0, DefWindowProcA) X(0, ShowWindow) \
    X(0, SetWindowLongA) X(0, GetWindowLongA) X(0, BeginPaint) X(0, EndPaint) X(0, InvalidateRect) \
    X(0, LoadBitmapA) X(0, LoadCursorA) X(0, SendMessageA) X(0, GetDlgItem) X(0, SetWindowTextA) \
    X(0, GetAncestor) X(0, ReleaseCapture) X(0, UpdateWindow) X(0, SetCapture) X(0, SetTimer) X(0, KillTimer) X(0, ScreenToClient) X(0, SetFocus) \
    X(1, SetBkMode) X(1, CreateCompatibleBitmap) X(1, CreateCompatibleDC) X(1, SelectObject) X(1, BitBlt) X(1, DeleteDC) X(1, DeleteObject) X(1, GetStockObject) \
    X(2, InitCommonControlsEx)
enum {
#define X(m, n) A_##n,
    APIS
#undef X
    A_COUNT
};
static PTR api[A_COUNT];
#define CALL(n, t) ((t)api[A_##n])
#define STD(r, ...) r (WINAPI *)(__VA_ARGS__)

/* ---- per-instance state ---------------------------------------------------------------------------------- */
#define NED 16
typedef struct Ed {
    AEffect *e;                 /* claimed with compare-and-swap */
    PTR panel, setup, parent, tab, font;
    PTR inst, buf;
    PTR pics[2][8];             /* [skin] 0 panel (111), DLL bitmaps 104 SETUP, 106 meter stages, 107 digits, 108 lamps,
                                   109 meter screen; added by the patch: 130 pressed buttons / dash, 131 white digits.
                                   Skin 1 (Modern): the same ids + 100 */
    PTR bmp, *parts;            /* the current skin's panel and parts */
    int chn, held, wheel;       /* control row: channel 0-15, held button (btn codes), wheel remainder */
    int vals[7];                /* parameter values shown on the Setup page (not yet applied) */
    int press;                  /* SETUP button held */
    float lv[18], hit[16];      /* meter levels 0..8 (16 channels, L, R), last hit per channel */
    u8 seq[16];
} Ed;
/* shared with params.asm (ed_share): sounding notes (key << 8 | channel), velocity and hit counter of the last
   note-on per channel, lamp mode (0 none, 1 XG, 2 GS), parameter values. The engine state of params.asm is one per
   DLL copy, so these are too. */
typedef struct { i32 *ncount; u32 *notes; u8 *mhit, *mseq; i32 *lampm, *ivals; u8 *prg, *msb, *lsb; u32 *pq; volatile u32 *pq_head, *pq_tail; i32 *skin; } Share;
static Share *sh;
static volatile float pk[2];    /* output peaks since the last meter update (audio thread writes, editor reads) */
static const u16 part_id[8] = { 111, 104, 106, 107, 108, 109, 130, 131 };
static Ed eds[NED];
static u32 loaded, cls_ok;
static char cls_panel[24], cls_setup[24];
static ERect rect = { 0, 0, 114, 400 };

#define NPAR 7
static const int pmax[NPAR] = { 248, 1, 1, 48, 200, 48, 4 };
static const int pdef[NPAR] = { 248, 1, 1, 24, 100, 24, 3 };

/* ---- small helpers --------------------------------------------------------------------------------------- */
void *memset(void *d, int c, u32 n) __attribute__((used));
void *memset(void *d, int c, u32 n) { u8 *p = d; while (n--) *p++ = (u8)c; return d; }
static void put_hex(char *d, u32 v) { for (int i = 7; i >= 0; i--) { d[7 - i] = "0123456789ABCDEF"[(v >> (i * 4)) & 15]; } d[8] = 0; }
static void put_int(char *d, int v, int sign) {
    char t[12]; int n = 0, k = 0;
    if (v < 0) { d[k++] = '-'; v = -v; } else if (sign && v > 0) d[k++] = '+';
    do { t[n++] = (char)('0' + v % 10); v /= 10; } while (v);
    while (n) d[k++] = t[--n];
    d[k] = 0;
}
static void put_str(char *d, const char *s) { while ((*d++ = *s++)); }

static Ed *find_ed(AEffect *e) { for (int i = 0; i < NED; i++) if (eds[i].e == e) return &eds[i]; return NULL; }
static Ed *claim_ed(AEffect *e) {
    for (int i = 0; i < NED; i++)
        if (__sync_val_compare_and_swap(&eds[i].e, (AEffect *)NULL, e) == NULL) return &eds[i];
    return NULL;
}

static int load_apis(u32 base) {
    if (loaded) return 1;
    PTR (WINAPI *gmh)(const char *) = *(PTR *)(base + 0x57040);
    PTR (WINAPI *gpa)(PTR, const char *) = *(PTR *)(base + 0x5703C);
    PTR (WINAPI *lla)(const char *) = gpa(gmh("kernel32.dll"), "LoadLibraryA");
    PTR mod[3] = { lla("user32.dll"), lla("gdi32.dll"), lla("comctl32.dll") };
    static const char *const names[] = {
#define X(m, n) #n,
        APIS
#undef X
    };
    static const u8 mods[] = {
#define X(m, n) m,
        APIS
#undef X
    };
    for (int i = 0; i < A_COUNT; i++) {
        if (!mod[mods[i]]) return 0;
        api[i] = gpa(mod[mods[i]], names[i]);
        if (!api[i]) return 0;
    }
    INITCC cc = { 8, 0x4 | 0x8 | 0x10 };   /* ICC_BAR_CLASSES | ICC_TAB_CLASSES | ICC_UPDOWN... enough for trackbar / tab */
    CALL(InitCommonControlsEx, STD(int, INITCC *))(&cc);
    loaded = 1;
    return 1;
}

static PTR mkwin(u32 ex, const char *cls, const char *text, u32 style, int x, int y, int w, int h, PTR parent, int id, PTR inst, PTR param) {
    return CALL(CreateWindowExA, STD(PTR, u32, const char *, const char *, u32, int, int, int, int, PTR, PTR, PTR, PTR))
           (ex, cls, text, style, x, y, w, h, parent, (PTR)(u32)id, inst, param);
}
static i32 snd(PTR h, u32 m, u32 w, i32 l) { return CALL(SendMessageA, STD(i32, PTR, u32, u32, i32))(h, m, w, l); }

/* draw rows [sy, sy + h) of the panel bitmap at (dx, dy) */
static void blit(Ed *d, PTR dc, int dx, int dy, int w, int h, int sx, int sy) {
    PTR mem = CALL(CreateCompatibleDC, STD(PTR, PTR))(dc);
    PTR old = CALL(SelectObject, STD(PTR, PTR, PTR))(mem, d->bmp);
    CALL(BitBlt, STD(int, PTR, int, int, int, int, PTR, int, int, u32))(dc, dx, dy, w, h, mem, sx, sy, SRCCOPY);
    CALL(SelectObject, STD(PTR, PTR, PTR))(mem, old);
    CALL(DeleteDC, STD(int, PTR))(mem);
}

/* ---- Setup page ------------------------------------------------------------------------------------------ */
enum { ID_POLY = 100, ID_POLYV, ID_REV, ID_CHO, ID_VOL, ID_VOLV, ID_TUNE, ID_TUNEV, ID_TRA, ID_TRAV,
       ID_RST = 120 /* 5 buttons */, ID_DEF = 130, ID_OK, ID_CANCEL, ID_APPLY, ID_ABOUT = 140 /* 6 statics */ };
#define SETUP_W 400
#define SETUP_H 570

static void text_of(int id, int v, char *out) {
    out[0] = 0;
    if (id == ID_POLYV) put_int(out, 8 + v, 0);
    else if (id == ID_VOLV) { int h = v - 24; if (h < 0) { out[0] = '-'; h = -h; put_int(out + 1, h / 2, 0); } else put_int(out, h / 2, 0);
                              char *e = out; while (*e) e++; if (h & 1) put_str(e, ".5"); else *e = 0; }
    else if (id == ID_TUNEV) put_int(out, v - 100, 0);
    else if (id == ID_TRAV) put_int(out, v - 24, 0);
}
static void show_val(Ed *d, int id, int v) {
    char t[16]; text_of(id, v, t);
    CALL(SetWindowTextA, STD(int, PTR, const char *))(CALL(GetDlgItem, STD(PTR, PTR, int))(d->setup, id), t);
}
static void set_ctl(Ed *d, int idx, int v) {          /* parameter index -> control */
    static const int slider[NPAR] = { ID_POLY, 0, 0, ID_VOL, ID_TUNE, ID_TRA, 0 };
    static const int label[NPAR] = { ID_POLYV, 0, 0, ID_VOLV, ID_TUNEV, ID_TRAV, 0 };
    PTR h = d->setup;
    d->vals[idx] = v;
    if (slider[idx]) { snd(CALL(GetDlgItem, STD(PTR, PTR, int))(h, slider[idx]), TBM_SETPOS, 1, v); show_val(d, label[idx], v); }
    else if (idx == 1) snd(CALL(GetDlgItem, STD(PTR, PTR, int))(h, ID_REV), BM_SETCHECK, v, 0);
    else if (idx == 2) snd(CALL(GetDlgItem, STD(PTR, PTR, int))(h, ID_CHO), BM_SETCHECK, v, 0);
}
static int read_ctl(Ed *d, int idx) {
    static const int slider[NPAR] = { ID_POLY, 0, 0, ID_VOL, ID_TUNE, ID_TRA, 0 };
    PTR h = d->setup;
    if (slider[idx]) return snd(CALL(GetDlgItem, STD(PTR, PTR, int))(h, slider[idx]), TBM_GETPOS, 0, 0);
    if (idx == 1) return snd(CALL(GetDlgItem, STD(PTR, PTR, int))(h, ID_REV), BM_GETCHECK, 0, 0) ? 1 : 0;
    if (idx == 2) return snd(CALL(GetDlgItem, STD(PTR, PTR, int))(h, ID_CHO), BM_GETCHECK, 0, 0) ? 1 : 0;
    return d->vals[idx];
}
static int get_par(Ed *d, int idx) { float f = d->e->getParameter(d->e, idx); return (int)(f * pmax[idx] + 0.5f); }
static void set_par(Ed *d, int idx, int v) { d->e->setParameter(d->e, idx, (float)v / (float)pmax[idx]); }
static void apply(Ed *d) { for (int i = 0; i < 6; i++) set_par(d, i, read_ctl(d, i)); }

static void tab_show(Ed *d, int tab) {                  /* 0 Settings, 1 About */
    for (int id = ID_POLY; id <= ID_RST + 4; id++) {
        PTR c = CALL(GetDlgItem, STD(PTR, PTR, int))(d->setup, id);
        if (c) CALL(ShowWindow, STD(int, PTR, int))(c, tab == 0 ? 5 : 0);
    }
    for (int id = 200; id < 210; id++) {                /* group boxes and captions of the Settings tab */
        PTR c = CALL(GetDlgItem, STD(PTR, PTR, int))(d->setup, id);
        if (c) CALL(ShowWindow, STD(int, PTR, int))(c, tab == 0 ? 5 : 0);
    }
    PTR c = CALL(GetDlgItem, STD(PTR, PTR, int))(d->setup, ID_DEF);
    if (c) CALL(ShowWindow, STD(int, PTR, int))(c, tab == 0 ? 5 : 0);
    for (int id = ID_ABOUT; id < ID_ABOUT + 6; id++) {
        c = CALL(GetDlgItem, STD(PTR, PTR, int))(d->setup, id);
        if (c) CALL(ShowWindow, STD(int, PTR, int))(c, tab == 1 ? 5 : 0);
    }
}

static i32 WINAPI setup_proc(PTR h, u32 m, u32 w, i32 l) {
    Ed *d = (Ed *)CALL(GetWindowLongA, STD(i32, PTR, int))(h, GWL_USERDATA);
    switch (m) {
    case WM_ERASEBKGND: break;
    case 0x138: case 0x135: case 0x133:                         /* WM_CTLCOLORSTATIC / BTN / EDIT: white like the tab page */
        CALL(SetBkMode, STD(int, PTR, int))((PTR)w, 1);
        return (i32)CALL(GetStockObject, STD(PTR, int))(0);     /* WHITE_BRUSH */
    case WM_PAINT: {
        PAINTSTRUCT ps;
        PTR dc = CALL(BeginPaint, STD(PTR, PTR, PAINTSTRUCT *))(h, &ps);
        if (d && d->bmp) blit(d, dc, 0, 0, 400, 24, 0, 0);           /* title strip of the panel */
        CALL(EndPaint, STD(int, PTR, PAINTSTRUCT *))(h, &ps);
        return 0;
    }
    case WM_LBUTTONDOWN:                                        /* the title strip drags the window */
        if (((l >> 16) & 0xFFFF) < 24) {
            CALL(ReleaseCapture, STD(int, void))();
            snd(h, 0xA1 /* WM_NCLBUTTONDOWN */, HTCAPTION, 0);
        }
        return 0;
    case WM_HSCROLL: {
        if (!d) break;
        PTR c = (PTR)l; int pos = (int)snd(c, TBM_GETPOS, 0, 0);
        if (c == CALL(GetDlgItem, STD(PTR, PTR, int))(h, ID_POLY)) show_val(d, ID_POLYV, pos);
        else if (c == CALL(GetDlgItem, STD(PTR, PTR, int))(h, ID_VOL)) show_val(d, ID_VOLV, pos);
        else if (c == CALL(GetDlgItem, STD(PTR, PTR, int))(h, ID_TUNE)) show_val(d, ID_TUNEV, pos);
        else if (c == CALL(GetDlgItem, STD(PTR, PTR, int))(h, ID_TRA)) show_val(d, ID_TRAV, pos);
        return 0;
    }
    case WM_NOTIFY:
        if (d && ((NMHDR *)l)->code == TCN_SELCHANGE) tab_show(d, (int)snd(d->tab, TCM_GETCURSEL, 0, 0));
        return 0;
    case WM_COMMAND: {
        int id = (int)(w & 0xFFFF);
        if (!d) break;
        if (id >= ID_RST && id < ID_RST + 5) { set_par(d, 6, id - ID_RST); return 0; }   /* Send Reset: at once */
        if (id == ID_DEF) { for (int i = 0; i < 6; i++) set_ctl(d, i, pdef[i]); return 0; }
        if (id == ID_APPLY) { apply(d); return 0; }
        if (id == ID_OK) { apply(d); CALL(ShowWindow, STD(int, PTR, int))(h, 0); return 0; }
        if (id == ID_CANCEL) { CALL(ShowWindow, STD(int, PTR, int))(h, 0); return 0; }
        break;
    }
    case WM_CLOSE: CALL(ShowWindow, STD(int, PTR, int))(h, 0); return 0;
    }
    return CALL(DefWindowProcA, STD(i32, PTR, u32, u32, i32))(h, m, w, l);
}

static PTR ctl(Ed *d, const char *cls, const char *text, u32 style, int x, int y, int w, int h, int id) {
    PTR c = mkwin(0, cls, text, style | WS_CHILD | WS_VISIBLE, x, y, w, h, d->setup, id, d->inst, NULL);
    if (c && d->font) snd(c, WM_SETFONT, (u32)d->font, 1);
    return c;
}
static void slider(Ed *d, int id, int y, int max, int tic) {
    PTR c = ctl(d, "msctls_trackbar32", "", WS_TABSTOP | 0x0 /* TBS_HORZ | TBS_AUTOTICKS */ | 1, 34, y, 214, 26, id);
    snd(c, TBM_SETRANGE, 1, max << 16);
    snd(c, TBM_SETTICFREQ, tic, 0);
    snd(c, TBM_SETPAGESIZE, 0, tic > 1 ? tic / 4 : 1);
}
static void group(Ed *d, const char *title, int y, int h, int id) { ctl(d, "BUTTON", title, BS_GROUPBOX, 18, y, 364, h, id); }

static void build_setup(Ed *d) {
    PTR h = d->setup;
    d->font = CALL(GetStockObject, STD(PTR, int))(17);           /* DEFAULT_GUI_FONT */
    TCITEMA ti; memset(&ti, 0, sizeof ti);
    d->tab = mkwin(0, "SysTabControl32", "", WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS | WS_TABSTOP, 8, 32, 384, SETUP_H - 32 - 56, h, 99, d->inst, NULL);
    if (d->tab) snd(d->tab, WM_SETFONT, (u32)d->font, 1);
    ti.mask = 1; ti.text = "Settings"; snd(d->tab, TCM_INSERTITEMA, 0, (i32)&ti);
    ti.text = "About";    snd(d->tab, TCM_INSERTITEMA, 1, (i32)&ti);
    int y = 70;
    group(d, "Polyphony", y, 56, 200);              slider(d, ID_POLY, y + 18, 248, 31);
    ctl(d, "STATIC", "", WS_BORDER | SS_CENTER | SS_CENTERIMAGE, 262, y + 20, 48, 22, ID_POLYV);          y += 66;
    group(d, "Effects", y, 44, 201);
    ctl(d, "BUTTON", "Reverb (CC 91)", BS_AUTOCHECKBOX | WS_TABSTOP, 34, y + 18, 140, 18, ID_REV);
    ctl(d, "BUTTON", "Chorus (CC 93)", BS_AUTOCHECKBOX | WS_TABSTOP, 190, y + 18, 140, 18, ID_CHO);          y += 54;
    group(d, "Output Level", y, 56, 202);           slider(d, ID_VOL, y + 18, 48, 24);
    ctl(d, "STATIC", "", WS_BORDER | SS_CENTER | SS_CENTERIMAGE, 262, y + 20, 48, 22, ID_VOLV);
    ctl(d, "STATIC", "dB", SS_CENTERIMAGE, 316, y + 20, 60, 22, 203);                                         y += 66;
    group(d, "Master Tune", y, 56, 204);            slider(d, ID_TUNE, y + 18, 200, 100);
    ctl(d, "STATIC", "", WS_BORDER | SS_CENTER | SS_CENTERIMAGE, 262, y + 20, 48, 22, ID_TUNEV);
    ctl(d, "STATIC", "cent", SS_CENTERIMAGE, 316, y + 20, 60, 22, 205);                                       y += 66;
    group(d, "Transpose", y, 56, 206);              slider(d, ID_TRA, y + 18, 48, 24);
    ctl(d, "STATIC", "", WS_BORDER | SS_CENTER | SS_CENTERIMAGE, 262, y + 20, 48, 22, ID_TRAV);
    ctl(d, "STATIC", "semitones", SS_CENTERIMAGE, 316, y + 20, 64, 22, 207);                                  y += 66;
    group(d, "Send Reset", y, 50, 208);
    static const char *const rst[5] = { "MT-32", "GM", "GS", "XGLite", "GM2" };
    for (int i = 0; i < 5; i++) ctl(d, "BUTTON", rst[i], WS_TABSTOP, 30 + i * 70, y + 18, 62, 24, ID_RST + i);
    y += 60;
    ctl(d, "BUTTON", "Set Defaults", WS_TABSTOP, 282, y, 100, 24, ID_DEF);
    ctl(d, "BUTTON", "OK", BS_DEFPUSHBUTTON | WS_TABSTOP, 26, SETUP_H - 44, 86, 26, ID_OK);
    ctl(d, "BUTTON", "Cancel", WS_TABSTOP, 124, SETUP_H - 44, 86, 26, ID_CANCEL);
    ctl(d, "BUTTON", "Apply", WS_TABSTOP, 222, SETUP_H - 44, 86, 26, ID_APPLY);
    static const char *const about[6] = { "S-YXG2006LE", "Yamaha's own engine and tables, unchanged.",
        "Patched by SXG-Create-NF: host lock removed,", "VST parameters, up to 256 voices, this editor.",
        "https://github.com/NightFright2k19/SXG-Create-NF", "" };
    for (int i = 0; i < 6; i++) ctl(d, "STATIC", about[i], 0, 30, 80 + i * 22, 340, 20, ID_ABOUT + i);
    tab_show(d, 0);
}

static void open_setup(Ed *d) {
    if (d->setup) {                                              /* already built: show again with current values */
        for (int i = 0; i < 6; i++) set_ctl(d, i, get_par(d, i));
        CALL(ShowWindow, STD(int, PTR, int))(d->setup, 5);
        return;
    }
    PTR owner = CALL(GetAncestor, STD(PTR, PTR, u32))(d->panel, 2);        /* GA_ROOT */
    d->setup = mkwin(WS_EX_TOOLWINDOW, cls_setup, "S-YXG2006LE Setup", WS_POPUP | WS_BORDER | WS_CLIPSIBLINGS,
                     120, 120, SETUP_W, SETUP_H, owner, 0, d->inst, NULL);
    if (!d->setup) return;
    CALL(SetWindowLongA, STD(i32, PTR, int, i32))(d->setup, GWL_USERDATA, (i32)d);
    build_setup(d);
    for (int i = 0; i < 6; i++) set_ctl(d, i, get_par(d, i));
    CALL(ShowWindow, STD(int, PTR, int))(d->setup, 5);
    CALL(UpdateWindow, STD(int, PTR))(d->setup);
}

/* ---- panel ----------------------------------------------------------------------------------------------- */
/* positions (panel 400 x 114) found in the DLL's panel bitmap: meter screen (bitmap 109) at 11, 57; meter columns
   (bitmap 106: 9 stages of 11 x 28) at x 19 + 11 * channel, L 205, R 216, y 62; POLYPHONY digits (bitmap 131,
   the white digits of the control row, 10 x 13) at x 257 / 267 / 277, y 73; lamps (bitmap 108: XG off / on, GS off / on, 40 x 39) at 308 / 350, y 48;
   SETUP (bitmap 104: pressed / normal, 80 x 16) at 309, 88 */
static const float lr_th[8] = { 0.0056f, 0.01f, 0.0178f, 0.0316f, 0.0562f, 0.1f, 0.178f, 0.316f };   /* -45 ... -10 dBFS */

static void meters_step(Ed *d) {
    for (int c = 0; c < 16; c++) {
        u8 q = sh->mseq[c];
        if (q != d->seq[c]) {
            d->seq[c] = q;
            float v = (float)sh->mhit[c] * (8.0f / 127.0f);
            d->hit[c] = v;
            if (v > d->lv[c]) d->lv[c] = v;
        }
        int held = 0, n = *sh->ncount;
        if (n > 256) n = 256;
        for (int i = 0; i < n && !held; i++) held = (int)(sh->notes[i] & 0xF) == c;
        if (held) { float t = d->hit[c] * 0.6f; d->lv[c] -= 0.15f; if (d->lv[c] < t) d->lv[c] = t; }
        else { d->lv[c] -= 0.5f; if (d->lv[c] < 0) d->lv[c] = 0; }
    }
    for (int i = 0; i < 2; i++) {
        float p = pk[i]; pk[i] = 0;
        int st = 0; while (st < 8 && p >= lr_th[st]) st++;
        if ((float)st > d->lv[16 + i]) d->lv[16 + i] = (float)st;
        else { d->lv[16 + i] -= 0.5f; if (d->lv[16 + i] < 0) d->lv[16 + i] = 0; }
    }
}

/* control row (as the MU plugins' panel, #42): buttons 15 x 15 in row 31; codes 1 / 2 PRG down / up, 3 / 4 CHN,
   5 / 6 MSB, 7 / 8 LSB; digits (bitmap 131, 10 x 13) in row 32 at 46 (CHN), 137 (PRG), 242 (MSB), 344 (LSB).
   A PRG step sends a program change, an MSB / LSB step a bank select followed by the program change of the current
   program, so the new bank sounds at once. A bank value the engine ignores in its mode (GM: MSB and LSB, GS: LSB)
   shows "---" and is not sent. The values shown are what the plugin last sent on that channel (params.asm trk):
   host events and the panel's own, once the audio thread has passed them on. */
static const int btn_x[8] = { 116, 174, 25, 73, 221, 279, 323, 381 };
static int bank_ok(int lsb) { int m = *sh->lampm; return m == 0 ? 0 : (m == 2 ? !lsb : 1); }
static void queue_msg(u32 msg) {
    u32 h = *sh->pq_head;
    if (h - *sh->pq_tail >= 32) return;                               /* full: the audio thread is not running */
    sh->pq[h & 31] = msg;
    __sync_synchronize();
    *sh->pq_head = h + 1;
}
static void step(Ed *d, int code) {
    int c = d->chn, dir = (code & 1) ? -1 : 1;
    switch ((code + 1) / 2) {
    /* the shown values change only when the audio thread hands the event to the engines (params.asm trk) */
    case 1: queue_msg(0xC0 | c | (u32)((sh->prg[c] + dir) & 127) << 8); break;
    case 2: d->chn = (c + dir) & 15; break;
    case 3: case 4: {
        int lsb = code >= 7;
        if (!bank_ok(lsb)) break;
        u8 *b = lsb ? sh->lsb : sh->msb;
        queue_msg(0xB0 | c | (u32)(lsb ? 32 : 0) << 8 | (u32)((b[c] + dir) & 127) << 16);
        queue_msg(0xC0 | c | (u32)sh->prg[c] << 8);
        break;
    }
    }
}
static int btn_at(int x, int y) {
    if (y < 31 || y >= 46) return 0;
    for (int i = 0; i < 8; i++) if (x >= btn_x[i] && x < btn_x[i] + 15) return i + 1;
    return 0;
}
static int group_at(int x, int y) {                                   /* wheel: 1 PRG, 2 CHN, 3 MSB, 4 LSB */
    if (y < 31 || y >= 46) return 0;
    if (x >= 25 && x <= 87) return 2;
    if (x >= 116 && x <= 188) return 1;
    if (x >= 221 && x <= 293) return 3;
    if (x >= 323 && x <= 395) return 4;
    return 0;
}

/* skin (#52 for the MU plugins): a click on the YAMAHA logo (x 8-103, y 0-22) switches; params.asm keeps the choice in
   the plugin state. A skin whose pictures are missing falls back to the original one. */
static void use_skin(Ed *d) {
    int k = (sh && (*sh->skin & 1) && d->pics[1][0]) ? 1 : 0;
    d->bmp = d->pics[k][0]; d->parts = &d->pics[k][1];
}

static void paint_panel(Ed *d, PTR dc) {
    PTR mem = CALL(CreateCompatibleDC, STD(PTR, PTR))(dc);
    if (!d->buf) d->buf = CALL(CreateCompatibleBitmap, STD(PTR, PTR, int, int))(dc, 400, 114);
    PTR oldm = CALL(SelectObject, STD(PTR, PTR, PTR))(mem, d->buf);
    PTR src = CALL(CreateCompatibleDC, STD(PTR, PTR))(dc);
    PTR olds = CALL(SelectObject, STD(PTR, PTR, PTR))(src, d->bmp);
#define BLT(dx, dy, w, h, sx, sy) CALL(BitBlt, STD(int, PTR, int, int, int, int, PTR, int, int, u32))(mem, dx, dy, w, h, src, sx, sy, SRCCOPY)
#define SEL(b) CALL(SelectObject, STD(PTR, PTR, PTR))(src, b)
    BLT(0, 0, 400, 114, 0, 0);
    if (d->parts[4]) { SEL(d->parts[4]); BLT(11, 57, 288, 47, 0, 0); }
    if (d->parts[1]) {
        SEL(d->parts[1]);
        for (int c = 0; c < 18; c++) {
            int st = (int)(d->lv[c] + 0.5f); if (st > 8) st = 8; if (st < 0) st = 0;
            int x = c < 16 ? 19 + 11 * c : (c == 16 ? 205 : 216);
            BLT(x, 62, 11, 28, st * 11, 0);
        }
    }
    if (d->parts[6] && sh) {                                         /* white digits like the control row */
        SEL(d->parts[6]);
        int n = *sh->ncount; if (n < 0) n = 0; if (n > 999) n = 999;
        for (int i = 0, x = 277; i < 3; i++, x -= 10) {
            if (i > 0 && n == 0) break;                              /* no leading zeros */
            BLT(x, 73, 10, 13, (n % 10) * 10, 0);
            n /= 10;
        }
    }
    if (d->parts[3] && sh) {
        SEL(d->parts[3]);
        int m = *sh->lampm;
        BLT(308, 48, 40, 39, m == 1 ? 40 : 0, 0);
        BLT(350, 48, 40, 39, m == 2 ? 120 : 80, 0);
    }
    if (d->parts[0]) { SEL(d->parts[0]); BLT(309, 88, 80, 16, d->press ? 0 : 80, 0); }
    if (d->parts[5] && d->parts[6] && sh) {                          /* control row: values, dashes, held button */
        int c = d->chn, vals[4] = { c + 1, sh->prg[c] + 1, sh->msb[c], sh->lsb[c] };
        static const int dx[4] = { 46, 137, 242, 344 }, nd[4] = { 2, 3, 3, 3 };
        for (int g = 0; g < 4; g++) {
            int dash = (g == 2 && !bank_ok(0)) || (g == 3 && !bank_ok(1)), v = vals[g];
            for (int i = nd[g] - 1, x = dx[g] + 10 * (nd[g] - 1); i >= 0; i--, x -= 10) {
                if (dash) { SEL(d->parts[5]); BLT(x, 32, 10, 13, 30, 0); }
                else { SEL(d->parts[6]); BLT(x, 32, 10, 13, (v % 10) * 10, 0); v /= 10; }
            }
        }
        if (d->held) { SEL(d->parts[5]); BLT(btn_x[d->held - 1], 31, 15, 15, (d->held & 1) ? 0 : 15, 0); }
    }
#undef BLT
#undef SEL
    CALL(SelectObject, STD(PTR, PTR, PTR))(src, olds);
    CALL(DeleteDC, STD(int, PTR))(src);
    CALL(BitBlt, STD(int, PTR, int, int, int, int, PTR, int, int, u32))(dc, 0, 0, 400, 114, mem, 0, 0, SRCCOPY);
    CALL(SelectObject, STD(PTR, PTR, PTR))(mem, oldm);
    CALL(DeleteDC, STD(int, PTR))(mem);
}

static int in_setup(i32 l) { int x = (short)(l & 0xFFFF), y = (short)((l >> 16) & 0xFFFF); return x >= 309 && x < 389 && y >= 88 && y < 104; }

static i32 WINAPI panel_proc(PTR h, u32 m, u32 w, i32 l) {
    Ed *d = (Ed *)CALL(GetWindowLongA, STD(i32, PTR, int))(h, GWL_USERDATA);
    switch (m) {
    case WM_ERASEBKGND: return 1;
    case WM_PAINT: {
        PAINTSTRUCT ps;
        PTR dc = CALL(BeginPaint, STD(PTR, PTR, PAINTSTRUCT *))(h, &ps);
        if (d) use_skin(d);
        if (d && d->bmp) paint_panel(d, dc);
        CALL(EndPaint, STD(int, PTR, PAINTSTRUCT *))(h, &ps);
        return 0;
    }
    case WM_TIMER:
        if (d && sh && w == 2 && d->held) {                           /* held button: repeat every 75 ms after 400 ms */
            step(d, d->held);
            CALL(SetTimer, STD(u32, PTR, u32, u32, PTR))(h, 2, 75, NULL);
        }
        if (d && sh && w == 1) meters_step(d);
        if (d && sh) CALL(InvalidateRect, STD(int, PTR, PTR, int))(h, NULL, 0);
        return 0;
    case WM_LBUTTONDOWN: {
        if (!d) return 0;
        CALL(SetFocus, STD(PTR, PTR))(h);
        int b = sh ? btn_at((short)(l & 0xFFFF), (short)((l >> 16) & 0xFFFF)) : 0;
        if (b) {
            d->held = b; step(d, b);
            CALL(SetCapture, STD(PTR, PTR))(h);
            CALL(SetTimer, STD(u32, PTR, u32, u32, PTR))(h, 2, 400, NULL);
        } else if (in_setup(l)) { d->press = 1; CALL(SetCapture, STD(PTR, PTR))(h); }
        else {
            int x = (short)(l & 0xFFFF), y = (short)((l >> 16) & 0xFFFF);
            if (sh && x >= 8 && x <= 103 && y >= 0 && y <= 22) {                /* YAMAHA logo: switch the skin */
                *sh->skin ^= 1; use_skin(d);
                if (d->setup) CALL(InvalidateRect, STD(int, PTR, PTR, int))(d->setup, NULL, 1);
            }
        }
        CALL(InvalidateRect, STD(int, PTR, PTR, int))(h, NULL, 0);
        return 0;
    }
    case WM_LBUTTONUP:
        if (d && d->held) {
            d->held = 0; CALL(KillTimer, STD(int, PTR, u32))(h, 2); CALL(ReleaseCapture, STD(int, void))();
            CALL(InvalidateRect, STD(int, PTR, PTR, int))(h, NULL, 0);
        }
        if (d && d->press) {
            d->press = 0; CALL(ReleaseCapture, STD(int, void))(); CALL(InvalidateRect, STD(int, PTR, PTR, int))(h, NULL, 0);
            if (in_setup(l)) open_setup(d);
        }
        return 0;
    case WM_MOUSEWHEEL: {
        if (!d || !sh) return 0;
        i32 pt[2] = { (short)(l & 0xFFFF), (short)((l >> 16) & 0xFFFF) };
        CALL(ScreenToClient, STD(int, PTR, i32 *))(h, pt);
        int g = group_at(pt[0], pt[1]);
        if (!g) return 0;
        d->wheel += (short)(w >> 16);
        while (d->wheel >= 120) { d->wheel -= 120; step(d, 2 * g); }
        while (d->wheel <= -120) { d->wheel += 120; step(d, 2 * g - 1); }
        CALL(InvalidateRect, STD(int, PTR, PTR, int))(h, NULL, 0);
        return 0;
    }
    }
    return CALL(DefWindowProcA, STD(i32, PTR, u32, u32, i32))(h, m, w, l);
}

/* ---- entry points (called by params.asm, cdecl) ------------------------------------------------------------ */
static void ed_free_pics(Ed *d) {
    for (int k = 0; k < 2; k++)
        for (int i = 0; i < 8; i++) if (d->pics[k][i]) { CALL(DeleteObject, STD(int, PTR))(d->pics[k][i]); d->pics[k][i] = NULL; }
}

int ed_getrect(AEffect *e, ERect **out) { (void)e; if (out) *out = &rect; return 1; }

int ed_open(AEffect *e, PTR parent, u32 base, Share *share) {
    sh = share;
    if (!load_apis(base) || find_ed(e)) return 0;
    if (!cls_ok) {
        put_str(cls_panel, "SXG2006P_"); put_hex(cls_panel + 9, base);
        put_str(cls_setup, "SXG2006S_"); put_hex(cls_setup + 9, base);
        WNDCLASSA wc; memset(&wc, 0, sizeof wc);
        wc.proc = (PTR)panel_proc; wc.inst = (PTR)base; wc.cls = cls_panel;
        wc.cursor = CALL(LoadCursorA, STD(PTR, PTR, PTR))(NULL, (PTR)32512);
        if (!CALL(RegisterClassA, STD(u16, WNDCLASSA *))(&wc)) return 0;
        wc.proc = (PTR)setup_proc; wc.cls = cls_setup; wc.brush = (PTR)(15 + 1);          /* COLOR_BTNFACE */
        if (!CALL(RegisterClassA, STD(u16, WNDCLASSA *))(&wc)) return 0;
        cls_ok = 1;
    }
    Ed *d = claim_ed(e);
    if (!d) return 0;
    d->inst = (PTR)base; d->parent = parent; d->setup = NULL; d->font = NULL; d->buf = NULL; d->press = 0; d->chn = 0; d->held = 0; d->wheel = 0;
    for (int i = 0; i < 18; i++) d->lv[i] = 0;
    for (int i = 0; i < 16; i++) { d->hit[i] = 0; d->seq[i] = sh->mseq[i]; }
    for (int k = 0; k < 2; k++)
        for (int i = 0; i < 8; i++) d->pics[k][i] = CALL(LoadBitmapA, STD(PTR, PTR, PTR))((PTR)base, (PTR)(u32)(part_id[i] + 100 * k));
    use_skin(d);
    d->panel = mkwin(0, cls_panel, "", WS_CHILD | WS_VISIBLE, 0, 0, 400, 114, parent, 0, d->inst, NULL);
    if (!d->panel) { ed_free_pics(d); d->e = NULL; return 0; }
    CALL(SetWindowLongA, STD(i32, PTR, int, i32))(d->panel, GWL_USERDATA, (i32)d);
    CALL(SetTimer, STD(u32, PTR, u32, u32, PTR))(d->panel, 1, 40, NULL);
    return 1;
}

void ed_close(AEffect *e) {
    Ed *d = find_ed(e);
    if (!d) return;
    if (d->setup) CALL(DestroyWindow, STD(int, PTR))(d->setup);
    if (d->panel) { CALL(KillTimer, STD(int, PTR, u32))(d->panel, 1); CALL(DestroyWindow, STD(int, PTR))(d->panel); }
    if (d->buf) CALL(DeleteObject, STD(int, PTR))(d->buf);
    for (int k = 0; k < 2; k++)
        for (int i = 0; i < 8; i++) if (d->pics[k][i]) { CALL(DeleteObject, STD(int, PTR))(d->pics[k][i]); d->pics[k][i] = NULL; }
    d->setup = d->panel = d->bmp = d->buf = NULL;
    __sync_synchronize();
    d->e = NULL;                                                  /* release the slot last */
}

void ed_idle(AEffect *e) { (void)e; }

/* audio thread (params.asm px_ret, after the output gain): output peaks for the L / R meters */
void ed_audio(float **outs, i32 n) {
    if (!outs || n <= 0) return;
    for (int c = 0; c < 2; c++) {
        float *o = outs[c], m = pk[c];
        if (!o) continue;
        for (int i = 0; i < n; i++) { float v = o[i] < 0 ? -o[i] : o[i]; if (v > m) m = v; }
        pk[c] = m;
    }
}

__asm__(".section .entry,\"ax\"\n"
        ".global ed_entries\ned_entries:\n"
        "jmp ed_getrect\n.balign 8\n"
        "jmp ed_open\n.balign 8\n"
        "jmp ed_close\n.balign 8\n"
        "jmp ed_idle\n.balign 8\n"
        "jmp ed_audio\n.balign 8\n"
        ".text\n");
