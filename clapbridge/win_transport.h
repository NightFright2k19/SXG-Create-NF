// win_transport.h - the Windows side of the link to the 32-bit helper (sxgbridge32.exe): start / stop it, one command, one audio block.
// Shared by the 64-bit CLAP bridge (clap_bridge.c, issue #97) and the 64-bit VST2 bridge (vst2_bridge.c, issue #104).
// Included after these definitions: <windows.h>, protocol.h, g_dir / g_stem (folder and plugin name of the bridge file), Inst (needs
// Shared* sh, int dead, active, char error[256], HANDLE proc, job, map, ready, ago, adone, cgo, cdone, SRWLOCK cmd_lock),
// find_dll(out, n) and SXG_KIND ("CLAP" or "plugin", used in messages).
#define HELPER_NAME L"sxgbridge32.exe"
static volatile LONG g_counter;
static int find_dll(wchar_t* out, size_t n);          // defined after this file: where the bridge looks for the plugin DLL
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

static int plat_start(Inst* p)
{
    wchar_t dllp[MAX_PATH], exe[MAX_PATH], cmd[3 * MAX_PATH], pfx[64];
    char pfx8[64];
    if (!find_dll(dllp, MAX_PATH)) { snprintf(p->error, sizeof p->error, "%ls.dll not found (see docs/clap.md for where it is searched)", g_stem); return 0; }
    _snwprintf(exe, MAX_PATH, L"%ls\\%ls", g_dir, HELPER_NAME);
    if (!file_exists(exe)) { snprintf(p->error, sizeof p->error, "sxgbridge32.exe not found next to the " SXG_KIND); return 0; }

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
