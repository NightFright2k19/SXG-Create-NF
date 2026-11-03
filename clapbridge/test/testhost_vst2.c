// testhost_vst2.c - minimal 64-bit VST2 host for testing the VST2 bridge (issue #104):  testhost_vst2.exe <plugin_x64.dll> [real]
// 'real': the plugin is one of the S-YXG DLLs, only load / process / editor / state are checked.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#include "../vst2.h"

static int fails;
#define CHECK(c, ...) do { if (!(c)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); fails++; } else { printf("ok:   "); printf(__VA_ARGS__); printf("\n"); } } while (0)

static intptr_t __cdecl master(AEffect* e, int32_t op, int32_t i, intptr_t v, void* p, float o) { (void)e; (void)i; (void)v; (void)p; (void)o; return op == audioMasterVersion ? 2400 : 0; }
typedef AEffect* (__cdecl *Entry)(AudioMasterCallback);

typedef struct { int32_t numEvents; intptr_t reserved; void* ev[4]; } Evs;
static float L[2048], R[2048];
static void run(AEffect* fx, Evs* e, int frames)
{
    float* out[2] = { L, R };
    if (e) fx->dispatcher(fx, effProcessEvents, 0, 0, e, 0);
    memset(L, 0x55, sizeof L); memset(R, 0x55, sizeof R);
    fx->processReplacing(fx, 0, out, frames);
}
static float peak(int a, int b) { float p = 0; for (int i = a; i < b; i++) if (fabsf(L[i]) > p) p = fabsf(L[i]); return p; }

int main(int argc, char** argv)
{
    int real = argc > 2;
    HMODULE m = LoadLibraryA(argv[1]);
    CHECK(m != 0, "load %s", argv[1]);
    if (!m) return 1;
    Entry entry = (Entry)GetProcAddress(m, "VSTPluginMain");
    CHECK(entry != 0, "VSTPluginMain exported");
    CHECK(GetProcAddress(m, "main") != 0, "main exported");
    AEffect* fx = entry(master);
    CHECK(fx && fx->magic == kEffectMagic, "plugin created");
    if (!fx) return 1;
    char name[64] = ""; fx->dispatcher(fx, effGetEffectName, 0, 0, name, 0);
    printf("      name=%s outputs=%d flags=%d id=%08x\n", name, fx->numOutputs, fx->flags, fx->uniqueID);
    CHECK(fx->numOutputs == 2 && (fx->flags & effFlagsIsSynth) && (fx->flags & 16), "2 outputs, synth, replacing");
    fx->dispatcher(fx, effOpen, 0, 0, 0, 0);
    fx->dispatcher(fx, effSetSampleRate, 0, 0, 0, 44100.0f);
    fx->dispatcher(fx, effSetBlockSize, 0, 2048, 0, 0);
    fx->dispatcher(fx, effMainsChanged, 0, 1, 0, 0);
    fx->dispatcher(fx, effStartProcess, 0, 0, 0, 0);

    VstMidiEvent on; memset(&on, 0, sizeof on);
    on.type = 1; on.byteSize = sizeof on; on.deltaFrames = 100; on.midiData[0] = (char)0x90; on.midiData[1] = 69; on.midiData[2] = 100;
    Evs e; memset(&e, 0, sizeof e); e.numEvents = 1; e.ev[0] = &on;
    run(fx, &e, 512);
    if (!real) {
        CHECK(peak(0, 100) == 0, "silence before the note (sample offset 100)");
        CHECK(peak(100, 512) > 0.4f, "note sounds after the offset (peak %.3f)", peak(100, 512));
        int zc = 0; for (int i = 101; i < 512; i++) if (L[i - 1] < 0 && L[i] >= 0) zc++;
        CHECK(zc >= 4 && zc <= 6, "pitch about 440 Hz (%d periods in 411 samples)", zc);
    } else printf("      peak of first block %.4f\n", peak(0, 512));

    if (!real) {
        char sx[10] = { (char)0xF0, 1, 2, 3, 4, 5, 6, 7, 8, (char)0xF7 };
        VstMidiSysexEvent sy; memset(&sy, 0, sizeof sy);
        sy.type = 6; sy.byteSize = sizeof sy; sy.dumpBytes = 10; sy.sysexDump = sx;
        e.numEvents = 1; e.ev[0] = &sy; run(fx, &e, 512);
        run(fx, 0, 512);
        CHECK(fabsf(peak(0, 512) - 1.0f) < 0.02f, "SysEx of 10 bytes sets gain 1.0 (peak %.3f)", peak(0, 512));
        VstMidiEvent off = on; off.deltaFrames = 0; off.midiData[0] = (char)0x80; off.midiData[2] = 0;
        e.ev[0] = &off; run(fx, &e, 512);
        CHECK(peak(0, 512) == 0, "note off silences");
        run(fx, 0, 2048);
    }

    void* chunk = 0;
    intptr_t n = fx->dispatcher(fx, effGetChunk, 0, 0, &chunk, 0);
    CHECK(n > 0 && chunk, "chunk get (%d bytes)", (int)n);
    if (!real) {
        CHECK(n == 8 && !memcmp(chunk, "initial", 8), "chunk holds the plugin's state");
        CHECK(fx->dispatcher(fx, effSetChunk, 0, 8, "changed", 0) == 1, "chunk set");
        n = fx->dispatcher(fx, effGetChunk, 0, 0, &chunk, 0);
        CHECK(n == 8 && !memcmp(chunk, "changed", 8), "chunk round trip");
    }

    CHECK(fx->flags & effFlagsHasEditor, "has editor");
    ERect* r = 0;
    CHECK(fx->dispatcher(fx, effEditGetRect, 0, 0, &r, 0) && r, "editor rect");
    int w = r ? r->right - r->left : 0, h = r ? r->bottom - r->top : 0;
    printf("      editor size %d x %d\n", w, h);
    if (!real) CHECK(w == 200 && h == 100, "editor size 200 x 100");
    HWND top = CreateWindowExA(0, "STATIC", "host", WS_OVERLAPPEDWINDOW | WS_VISIBLE, 0, 0, w + 20, h + 40, 0, 0, 0, 0);
    CHECK(fx->dispatcher(fx, effEditOpen, 0, 0, top, 0) == 1, "editor open");
    DWORD t0 = GetTickCount(); MSG msg;
    while (GetTickCount() - t0 < 1500) { while (PeekMessageA(&msg, 0, 0, 0, PM_REMOVE)) DispatchMessageA(&msg); Sleep(10); }
    CHECK(FindWindowExA(top, 0, 0, 0) != 0, "editor window is a child of the host window");
    fx->dispatcher(fx, effEditClose, 0, 0, 0, 0);
    fx->dispatcher(fx, effStopProcess, 0, 0, 0, 0);
    fx->dispatcher(fx, effMainsChanged, 0, 0, 0, 0);
    fx->dispatcher(fx, effClose, 0, 0, 0, 0);
    printf(fails ? "RESULT: %d failed\n" : "RESULT: all passed\n", fails);
    return fails != 0;
}
